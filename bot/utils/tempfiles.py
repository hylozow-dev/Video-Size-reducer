"""Helpers for creating and cleaning up per-job temporary storage.

Each incoming video gets its own subdirectory under `storage_dir` named by a
unique job id, containing the downloaded input file and the compressed
output file. This keeps concurrent jobs isolated and makes cleanup trivial.
"""
from __future__ import annotations

import logging
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def job_dir(storage_dir: Path, job_id: str) -> Path:
    """Return (creating if needed) an isolated directory for a compression job.

    Jobs live under `<storage_dir>/jobs/<job_id>` -- a dedicated subtree that
    never overlaps with the local Bot API server's own file storage (which,
    when enabled, is configured to use `<storage_dir>/telegram-bot-api`).
    This guarantees our cleanup logic can never delete files the Bot API
    server still considers "owned".
    """
    path = storage_dir / "jobs" / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_job_dir(storage_dir: Path, job_id: str) -> None:
    path = storage_dir / "jobs" / job_id
    if path.exists():
        try:
            shutil.rmtree(path)
        except OSError:
            logger.warning("Failed to clean up job directory: %s", path, exc_info=True)


@contextmanager
def job_workspace(storage_dir: Path) -> Iterator[tuple[str, Path]]:
    """Context manager yielding (job_id, job_dir) and cleaning up on exit."""
    job_id = new_job_id()
    path = job_dir(storage_dir, job_id)
    try:
        yield job_id, path
    finally:
        cleanup_job_dir(storage_dir, job_id)
