from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pytest

import pdf_size_fit.source_version as versions
from pdf_size_fit.source_version import (
    SourceChangedError, capture_source_version, frozen_source, require_source_version,
)


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    directory = tmp_path / "private-temp"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    return directory


def test_frozen_copy_is_verified_bounded_and_removed(tmp_path, scratch, monkeypatch):
    source = tmp_path / "synthetic.pdf"
    content = b"synthetic" * 300000
    source.write_bytes(content)
    version = capture_source_version(source)
    original_open = Path.open
    reads = []

    class BoundedReader:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def fileno(self):
            return self.stream.fileno()
        def read(self, size):
            assert 0 < size <= versions.COPY_CHUNK_BYTES
            reads.append(size)
            return self.stream.read(size)

    def guarded_open(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return BoundedReader(stream) if mode == "rb" else stream

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", guarded_open)
        with frozen_source(source, version) as snapshot:
            path = snapshot.path
            assert snapshot.original_path == source
            assert snapshot.version == version
            snapshot.require_current()
            with original_open(path, "rb") as stream:
                assert stream.read() == content
    assert reads and not path.exists() and not list(scratch.iterdir())
    assert source.read_bytes() == content


@pytest.mark.parametrize("atomic", [False, True])
def test_equal_length_restored_mtime_requires_content_and_identity(tmp_path, atomic):
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"OLD1")
    before = capture_source_version(source)
    stat = source.stat()
    if atomic:
        replacement = tmp_path / "replacement.pdf"
        replacement.write_bytes(b"NEW1")
        os.utime(replacement, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        replacement.replace(source)
    else:
        source.write_bytes(b"NEW1")
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(SourceChangedError, match="もう一度"):
        require_source_version(source, before)
    assert source.read_bytes() == b"NEW1"


def test_identical_bytes_atomic_replacement_changes_identity(tmp_path):
    source, other = tmp_path / "source.pdf", tmp_path / "other.pdf"
    source.write_bytes(b"same bytes")
    version = capture_source_version(source)
    other.write_bytes(b"same bytes")
    os.utime(other, ns=(source.stat().st_atime_ns, version.mtime_ns))
    other.replace(source)
    with pytest.raises(SourceChangedError):
        require_source_version(source, version)


def test_source_changes_inside_streamed_copy_is_refused_and_removed(tmp_path, scratch, monkeypatch):
    source = tmp_path / "synthetic.pdf"
    original = b"A" * (versions.COPY_CHUNK_BYTES * 3)
    replacement = b"B" * len(original)
    source.write_bytes(original)
    stat = source.stat()
    read = versions._read_version

    def during_copy(path, destination=None):
        if destination is None:
            return read(path)
        class ReplaceOnWrite:
            changed = False
            def write(self, data):
                result = destination.write(data)
                if not self.changed:
                    self.changed = True
                    source.write_bytes(replacement)
                    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                return result
        return read(path, ReplaceOnWrite())

    monkeypatch.setattr(versions, "_read_version", during_copy)
    with pytest.raises(SourceChangedError):
        with frozen_source(source):
            pytest.fail("changed snapshot accepted")
    assert source.read_bytes() == replacement and not list(scratch.iterdir())


@pytest.mark.parametrize("failure", ["copy-permission", "disk-full", "consumer"])
def test_snapshot_cleanup_on_failures(tmp_path, scratch, monkeypatch, failure):
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    read = versions._read_version
    def fail_copy(path, destination=None):
        if destination is not None:
            destination.write(b"partial")
            if failure == "copy-permission":
                raise PermissionError("synthetic permission error")
            raise OSError("synthetic no space left")
        return read(path)
    if failure != "consumer":
        monkeypatch.setattr(versions, "_read_version", fail_copy)
    with pytest.raises(RuntimeError):
        with frozen_source(source):
            raise RuntimeError("synthetic consumer failure")
    assert not list(scratch.iterdir()) and source.read_bytes() == b"synthetic"


def test_consumer_collision_keeps_original_exception(tmp_path, scratch):
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    with pytest.raises(FileExistsError):
        with frozen_source(source):
            raise FileExistsError("outside writer won")
    assert not list(scratch.iterdir())


def test_temp_space_creation_failure_has_retry_message(tmp_path, monkeypatch):
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    def unavailable(*args, **kwargs):
        raise OSError("synthetic temporary directory unavailable")
    monkeypatch.setattr(tempfile, "TemporaryDirectory", unavailable)
    with pytest.raises(SourceChangedError, match="もう一度"):
        with frozen_source(source):
            pytest.fail("no temp space")


def test_interruption_cleans_readonly_snapshot(tmp_path, scratch):
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    with pytest.raises(KeyboardInterrupt):
        with frozen_source(source):
            raise KeyboardInterrupt()
    assert not list(scratch.iterdir())
