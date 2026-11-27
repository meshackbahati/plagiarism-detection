import io
import tarfile
import zipfile

import pytest

from app.services.archive_extractor import ArchiveError, ArchiveExtractor

DOCS = {".txt", ".pdf", ".docx"}


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_zip_reads_supported_files_only():
    data = _zip({"a.txt": "hello", "dir/b.txt": "world", "c.exe": "x", "__MACOSX/._a.txt": "junk"})
    members, skipped = ArchiveExtractor.read_members(data, "x.zip", DOCS)
    assert sorted(m.name for m in members) == ["a.txt", "dir/b.txt"]
    assert any("c.exe" in s for s in skipped)


def test_zip_slip_entries_dropped():
    data = _zip({"../../etc/evil.txt": "x", "/abs.txt": "y", "ok.txt": "z"})
    members, _ = ArchiveExtractor.read_members(data, "x.zip", DOCS)
    assert [m.name for m in members] == ["ok.txt"]


def test_zip_bomb_total_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ARCHIVE_MAX_TOTAL_BYTES", 1000)
    data = _zip({f"{i}.txt": "a" * 400 for i in range(5)})
    with pytest.raises(ArchiveError):
        ArchiveExtractor.read_members(data, "bomb.zip", DOCS)


def test_zip_member_count_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ARCHIVE_MAX_FILES", 3)
    data = _zip({f"{i}.txt": "a" for i in range(10)})
    with pytest.raises(ArchiveError):
        ArchiveExtractor.read_members(data, "many.zip", DOCS)


def test_tar_skips_symlinks_and_reads_files():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo("essay.txt")
        payload = b"real essay"
        info.size = len(payload)
        t.addfile(info, io.BytesIO(payload))
        link = tarfile.TarInfo("passwd.txt")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        t.addfile(link)
    members, _ = ArchiveExtractor.read_members(buf.getvalue(), "x.tar.gz", DOCS)
    assert [(m.name, m.content) for m in members] == [("essay.txt", b"real essay")]


def test_damaged_archive():
    with pytest.raises(ArchiveError):
        ArchiveExtractor.read_members(b"PK\x03\x04 not really", "bad.zip", DOCS)


def test_is_archive():
    assert ArchiveExtractor.is_archive("a.TAR.GZ")
    assert ArchiveExtractor.is_archive("a.tgz")
    assert not ArchiveExtractor.is_archive("a.gz")
    assert not ArchiveExtractor.is_archive("a.pdf")
