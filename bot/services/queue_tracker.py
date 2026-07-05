"""Tracks the state of the single active compression job.

The bot enforces a hard limit of exactly **one** concurrent ffmpeg job at
all times (see `Settings.max_concurrent_jobs` in `bot/config.py`, which is
clamped to 1 no matter what is configured) to avoid overloading the host.
Every other user waits in a first-come-first-served queue.

This module lets newly arriving users be told roughly how long they'll
wait, based on the currently active job's real ffmpeg progress once
available, falling back to rougher estimates before that.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

# Rough fallback estimate (seconds) used for queued jobs that haven't
# started processing yet, since we don't know their video's actual
# duration until they reach the front of the queue and get probed.
FALLBACK_JOB_SECONDS = 120.0

# Fixed overhead added for the download + probe + upload phases, which
# happen outside of the ffmpeg progress-tracked compression phase.
OVERHEAD_SECONDS = 30.0


@dataclass
class _ActiveJob:
    started_at: float
    video_duration_sec: Optional[float] = None
    compression_started_at: Optional[float] = None
    progress_fraction: float = 0.0


class QueueTracker:
    """Process-wide tracker for the bot's single-job queue.

    Not thread-safe, but the bot runs a single asyncio event loop, so plain
    attribute access from coroutines is safe here.
    """

    def __init__(self) -> None:
        self._active: Optional[_ActiveJob] = None
        self._waiting_count: int = 0

    # --- active job lifecycle -------------------------------------------
    def start_job(self) -> None:
        self._active = _ActiveJob(started_at=time.monotonic())

    def set_video_duration(self, duration_sec: float) -> None:
        if self._active is not None:
            self._active.video_duration_sec = duration_sec

    def mark_compression_started(self) -> None:
        if self._active is not None:
            self._active.compression_started_at = time.monotonic()

    def update_progress(self, fraction: float) -> None:
        if self._active is not None:
            self._active.progress_fraction = fraction

    def finish_job(self) -> None:
        self._active = None

    @property
    def is_busy(self) -> bool:
        return self._active is not None

    # --- queue bookkeeping ------------------------------------------------
    def enter_queue(self) -> int:
        """Call when a new job starts waiting behind the active one.

        Returns this job's 1-based position in the waiting line (1 means
        "next up after the currently active job finishes").
        """
        self._waiting_count += 1
        return self._waiting_count

    def leave_queue(self) -> None:
        self._waiting_count = max(0, self._waiting_count - 1)

    @property
    def waiting_count(self) -> int:
        return self._waiting_count

    # --- estimation ---------------------------------------------------
    def estimate_active_job_remaining_seconds(self) -> Optional[float]:
        """Best-effort estimate of how long until the active job finishes.

        Returns None if there is no active job.
        """
        job = self._active
        if job is None:
            return None

        # Best case: ffmpeg is already reporting real progress, so we can
        # extrapolate from actual elapsed time and completion fraction.
        if job.compression_started_at is not None and job.progress_fraction > 0.02:
            elapsed = time.monotonic() - job.compression_started_at
            remaining = elapsed / job.progress_fraction - elapsed
            return max(remaining, 0.0) + 5.0  # small safety margin for upload

        # Compression hasn't reported meaningful progress yet, but we know
        # the video's duration (post-probe): assume compression takes
        # roughly as long as the video itself, plus fixed overhead.
        if job.video_duration_sec is not None:
            elapsed_total = time.monotonic() - job.started_at
            estimate = job.video_duration_sec + OVERHEAD_SECONDS
            return max(estimate - elapsed_total, OVERHEAD_SECONDS)

        # We don't even know the video's duration yet (still downloading).
        elapsed_total = time.monotonic() - job.started_at
        return max(FALLBACK_JOB_SECONDS - elapsed_total, OVERHEAD_SECONDS)

    def estimate_wait_seconds_for_position(self, position: int) -> float:
        """Estimate total wait time for someone at 1-based queue `position`.

        Position 1 means "right behind the active job" (no one else
        waiting ahead of them). Positions ahead of them whose videos
        haven't been probed yet are estimated using a rough flat fallback,
        since their actual duration is unknown.
        """
        remaining = self.estimate_active_job_remaining_seconds()
        if remaining is None:
            remaining = FALLBACK_JOB_SECONDS
        ahead_in_queue = max(position - 1, 0)
        return remaining + ahead_in_queue * FALLBACK_JOB_SECONDS


# Single process-wide instance shared by all handlers.
queue_tracker = QueueTracker()
