"""Bounded source-version checks shared by viewing consent and monochrome fitting."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
from typing import BinaryIO, Iterator


COPY_CHUNK_BYTES = 1024 * 1024
SOURCE_RETRY_MESSAGE = (
    "入力PDFが変更されたか、同じ版であることを確認できませんでした。"
    "変換を中止しました。入力PDFを確認して、もう一度選択・実行してください。"
)


class SourceChangedError(RuntimeError):
    """The approved input version cannot safely be used or published."""


@dataclass(frozen=True)
class SourceVersion:
    size_bytes: int
    sha256: str
    device: int
    inode: int
    mtime_ns: int
    ctime_ns: int


def _identity(stat: os.stat_result) -> tuple[int, ...]:
    # Windows fstat/stat can report different ctime meanings (change vs birth).
    # Do not equate those fields; content SHA, file ID, size and mtime still bind it.
    ctime_ns = stat.st_ctime_ns if os.name != "nt" else 0
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, ctime_ns)


def _read_version(path: Path, destination: BinaryIO | None = None) -> SourceVersion:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        while chunk := stream.read(COPY_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
            if destination is not None:
                destination.write(chunk)
        after = os.fstat(stream.fileno())
    # Check the pathname too: a new file can replace the still-open old descriptor.
    if _identity(before) != _identity(after) or _identity(after) != _identity(path.stat()):
        raise SourceChangedError(SOURCE_RETRY_MESSAGE)
    if size != after.st_size:
        raise SourceChangedError(SOURCE_RETRY_MESSAGE)
    return SourceVersion(size, digest.hexdigest(), after.st_dev, after.st_ino,
                         after.st_mtime_ns, _identity(after)[-1])


def capture_source_version(path: str | Path) -> SourceVersion:
    try:
        return _read_version(Path(path))
    except OSError as error:
        raise SourceChangedError(SOURCE_RETRY_MESSAGE) from error


def require_source_version(path: str | Path, expected: SourceVersion) -> None:
    if capture_source_version(path) != expected:
        raise SourceChangedError(SOURCE_RETRY_MESSAGE)


@dataclass(frozen=True)
class FrozenSource:
    original_path: Path
    path: Path
    version: SourceVersion

    def require_current(self) -> None:
        require_source_version(self.original_path, self.version)


@contextmanager
def frozen_source(
    path: str | Path, expected: SourceVersion | None = None,
) -> Iterator[FrozenSource]:
    """Capture, verify and privately retain one read-only on-disk PDF version.

    Three bounded streaming reads (before/copy/after) reject concurrent capture
    changes, including equal-length changes with restored mtime. This is version
    validation, not an OS lock excluding every external writer.
    """
    original = Path(path)
    before = capture_source_version(original)
    if expected is not None and before != expected:
        raise SourceChangedError(SOURCE_RETRY_MESSAGE)
    try:
        workspace = tempfile.TemporaryDirectory(prefix="pdf-size-fit-source-")
    except OSError as error:
        raise SourceChangedError(SOURCE_RETRY_MESSAGE) from error
    with workspace as directory:
        snapshot = Path(directory) / "source.pdf"
        try:
            try:
                with snapshot.open("xb") as destination:
                    copied = _read_version(original, destination)
                stored = capture_source_version(snapshot)
                if copied != before or (stored.size_bytes, stored.sha256) != (
                    before.size_bytes, before.sha256,
                ):
                    raise SourceChangedError(SOURCE_RETRY_MESSAGE)
                require_source_version(original, before)
                # All PDF consumers receive this path; it is never modified again.
                snapshot.chmod(0o400)
            except OSError as error:
                raise SourceChangedError(SOURCE_RETRY_MESSAGE) from error
            yield FrozenSource(original, snapshot, before)
        finally:
            # Windows cannot unlink a read-only file until its attribute is cleared.
            if snapshot.exists():
                snapshot.chmod(0o600)
