import zipfile
import tarfile
import os
from typing import List, Tuple
from pathlib import Path
import tempfile


class ArchiveExtractor:
    """Handles extraction of tar and zip archives with path traversal protection."""

    SUPPORTED_EXTENSIONS = {'.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2'}

    @staticmethod
    def is_archive(filename: str) -> bool:
        """Check if file is a supported archive"""
        path = Path(filename)
        # Check for compound extensions like .tar.gz
        if path.suffix == '.gz' and path.stem.endswith('.tar'):
            return True
        if path.suffix == '.bz2' and path.stem.endswith('.tar'):
            return True
        return path.suffix in ArchiveExtractor.SUPPORTED_EXTENSIONS

    @staticmethod
    def _is_safe_path(member_name: str, extract_to: str) -> bool:
        """Validate that an archive entry path doesn't escape the extraction directory."""
        # Reject absolute paths and path traversal
        if os.path.isabs(member_name):
            return False
        target = os.path.realpath(os.path.join(extract_to, member_name))
        return target.startswith(os.path.realpath(extract_to) + os.sep) or target == os.path.realpath(extract_to)

    @staticmethod
    def extract_archive(archive_path: str, extract_to: str = None) -> List[str]:
        """
        Extract archive and return list of extracted file paths.

        Includes path traversal protection to prevent zip-slip attacks.

        Args:
            archive_path: Path to the archive file
            extract_to: Directory to extract to (creates temp dir if None)

        Returns:
            List of paths to extracted files
        """
        if extract_to is None:
            extract_to = tempfile.mkdtemp()

        extracted_files = []
        path = Path(archive_path)

        try:
            if path.suffix == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    # Validate all entries before extraction
                    for name in zip_ref.namelist():
                        if not ArchiveExtractor._is_safe_path(name, extract_to):
                            print(f"Skipping unsafe zip entry: {name}")
                            continue
                    zip_ref.extractall(extract_to)
                    extracted_files = [
                        os.path.join(extract_to, name)
                        for name in zip_ref.namelist()
                        if not name.endswith('/') and ArchiveExtractor._is_safe_path(name, extract_to)
                    ]

            elif '.tar' in path.name:
                # Handles .tar, .tar.gz, .tar.bz2, etc.
                mode = 'r:*'  # Auto-detect compression
                with tarfile.open(archive_path, mode) as tar_ref:
                    # Filter out unsafe members before extraction
                    safe_members = []
                    for member in tar_ref.getmembers():
                        if not ArchiveExtractor._is_safe_path(member.name, extract_to):
                            print(f"Skipping unsafe tar entry: {member.name}")
                            continue
                        safe_members.append(member)
                    tar_ref.extractall(extract_to, members=safe_members)
                    extracted_files = [
                        os.path.join(extract_to, member.name)
                        for member in safe_members
                        if member.isfile()
                    ]
        except Exception as e:
            print(f"Error extracting archive {archive_path}: {e}")
            raise

        return extracted_files

    @staticmethod
    def extract_and_filter(archive_path: str, allowed_extensions: List[str] = None) -> List[Tuple[str, str]]:
        """
        Extract archive and filter files by extension.

        Args:
            archive_path: Path to archive
            allowed_extensions: List of allowed extensions (e.g., ['.txt', '.pdf'])

        Returns:
            List of tuples (original_filename, extracted_path)
        """
        extracted_files = ArchiveExtractor.extract_archive(archive_path)

        if allowed_extensions:
            filtered = []
            for fpath in extracted_files:
                ext = Path(fpath).suffix.lower()
                if ext in allowed_extensions:
                    filtered.append((Path(fpath).name, fpath))
            return filtered

        return [(Path(fpath).name, fpath) for fpath in extracted_files]
