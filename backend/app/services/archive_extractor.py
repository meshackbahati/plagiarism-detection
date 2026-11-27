"""
Safe archive extraction (zip, tar, tar.gz, tgz, tar.bz2).

Protects against:
- zip-slip / path traversal (absolute paths, "..", symlinks escaping the dir)
- zip bombs (caps on member count, per-file size and total uncompressed size)
- device files, FIFOs and links inside tarballs (only regular files are read)

Files are read straight from the archive into memory, never written to a
shared temp dir, so nothing is left behind if processing fails.
"""

from __future__ import annotations

import logging
import os
import posixpath
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class ArchiveError(Exception):
    """Archive is unreadable or exceeds safety limits. Message is user-facing."""


@dataclass
class ArchiveMember:
    name: str  # path inside the archive (posix, sanitised)
    content: bytes


class ArchiveExtractor:
    SUPPORTED_EXTENSIONS = {".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2"}

    @staticmethod
    def is_archive(filename: str) -> bool:
        name = (filename or "").lower()
        return any(name.endswith(ext) for ext in ArchiveExtractor.SUPPORTED_EXTENSIONS)

    @staticmethod
    def _safe_member_name(name: str) -> Optional[str]:
        """Return a normalised relative path, or None if the entry is unsafe/junk."""
        name = name.replace("\\", "/")
        if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
            return None
        norm = posixpath.normpath(name)
        if norm in ("", ".") or norm.startswith("../") or norm == "..":
            return None
        parts = PurePosixPath(norm).parts
        # macOS resource forks and hidden files are never documents.
        if any(p == "__MACOSX" or p.startswith("._") or p == ".DS_Store" for p in parts):
            return None
        return norm

    @staticmethod
    def _wanted(name: str, allowed_extensions: Optional[Iterable[str]]) -> bool:
        if not allowed_extensions:
            return True
        return os.path.splitext(name)[1].lower() in set(allowed_extensions)

    @classmethod
    def read_members(
        cls,
        archive_bytes: bytes,
        filename: str,
        allowed_extensions: Optional[Iterable[str]] = None,
    ) -> Tuple[List[ArchiveMember], List[str]]:
        """
        Read regular files from an archive held in memory.
        Returns (members, skipped_notes).
        """
        import io

        max_members = settings.ARCHIVE_MAX_FILES
        max_file = settings.ARCHIVE_MAX_FILE_BYTES
        max_total = settings.ARCHIVE_MAX_TOTAL_BYTES

        members: List[ArchiveMember] = []
        skipped: List[str] = []
        total = 0
        lower = filename.lower()

        def accept(name: str, size: int) -> bool:
            nonlocal total
            if len(members) >= max_members:
                raise ArchiveError(f"Archive has more than {max_members} files.")
            if size > max_file:
                skipped.append(f"{name}: larger than {max_file // (1024 * 1024)}MB")
                return False
            if total + size > max_total:
                raise ArchiveError(
                    f"Archive expands to more than {max_total // (1024 * 1024)}MB, refusing to extract."
                )
            total += size
            return True

        try:
            if lower.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        safe = cls._safe_member_name(info.filename)
                        if safe is None:
                            continue
                        if not cls._wanted(safe, allowed_extensions):
                            skipped.append(f"{safe}: unsupported file type")
                            continue
                        if info.flag_bits & 0x1:
                            skipped.append(f"{safe}: encrypted")
                            continue
                        if not accept(safe, info.file_size):
                            continue
                        # Read with a hard cap: file_size in the header can lie.
                        with zf.open(info) as fh:
                            data = fh.read(max_file + 1)
                        if len(data) > max_file:
                            skipped.append(f"{safe}: larger than declared")
                            continue
                        members.append(ArchiveMember(safe, data))
            else:
                with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as tf:
                    for info in tf:
                        if not info.isreg():  # skip dirs, links, devices, fifos
                            continue
                        safe = cls._safe_member_name(info.name)
                        if safe is None:
                            continue
                        if not cls._wanted(safe, allowed_extensions):
                            skipped.append(f"{safe}: unsupported file type")
                            continue
                        if not accept(safe, info.size):
                            continue
                        fh = tf.extractfile(info)
                        if fh is None:
                            continue
                        members.append(ArchiveMember(safe, fh.read(max_file + 1)[:max_file]))
        except ArchiveError:
            raise
        except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as exc:
            raise ArchiveError(f"Archive is damaged or not a valid {os.path.splitext(lower)[1]} file.") from exc
        except NotImplementedError as exc:  # unsupported zip compression
            raise ArchiveError(f"Archive uses an unsupported compression method ({exc}).") from exc

        return members, skipped

    # ── Backwards-compatible helpers (path based) ──

    @classmethod
    def extract_and_filter(cls, archive_path: str, allowed_extensions: List[str] = None) -> List[Tuple[str, bytes]]:
        with open(archive_path, "rb") as fh:
            members, _ = cls.read_members(fh.read(), archive_path, allowed_extensions)
        return [(m.name, m.content) for m in members]
