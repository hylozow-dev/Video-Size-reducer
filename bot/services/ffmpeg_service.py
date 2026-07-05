"""ffmpeg-based video compression service.

Supports two compression modes:

1. Quality presets (CRF-based, libx264) - simple, good default quality/size
   trade-off without needing to know the target size in advance.
2. Target file size - computes the required average video bitrate from the
   desired output size and the video duration, then encodes using a
   single-pass bitrate-constrained encode with a bounded VBV buffer so the
   result reliably lands close to (and under) the requested size.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Optional

from bot.services.media_info import VideoInfo

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float], Awaitable[None]]

# Reserve this much of the target size for the audio track + container
# overhead so the final file doesn't exceed the requested size.
_AUDIO_BITRATE_KBPS = 128
_CONTAINER_OVERHEAD_RATIO = 0.98  # keep 2% safety margin


class CompressionError(RuntimeError):
    """Raised when ffmpeg fails to produce an output file."""


class Preset(str, Enum):
    HIGH = "high"       # CRF 20 - minimal quality loss, moderate size reduction
    MEDIUM = "medium"    # CRF 26 - balanced
    LOW = "low"          # CRF 32 - aggressive size reduction

    @property
    def crf(self) -> int:
        return {Preset.HIGH: 20, Preset.MEDIUM: 26, Preset.LOW: 32}[self]

    @property
    def label(self) -> str:
        return {
            Preset.HIGH: "High quality (small size reduction)",
            Preset.MEDIUM: "Balanced quality/size",
            Preset.LOW: "Smallest size (lower quality)",
        }[self]


@dataclass(slots=True)
class CompressionPlan:
    """Describes how a video will be encoded."""

    mode: str  # "preset" | "target_size"
    preset: Optional[Preset] = None
    target_size_mb: Optional[float] = None
    video_bitrate_kbps: Optional[int] = None


def plan_for_preset(preset: Preset) -> CompressionPlan:
    return CompressionPlan(mode="preset", preset=preset)


def plan_for_target_size(info: VideoInfo, target_size_mb: float) -> CompressionPlan:
    """Compute the video bitrate required to hit `target_size_mb`.

    Raises ValueError if the target size is unreasonably small for the
    video's duration (i.e. would require a near-zero or negative bitrate).
    """
    duration = max(info.duration_sec, 1.0)
    audio_kbps = _AUDIO_BITRATE_KBPS if info.has_audio else 0

    total_kbps_budget = (target_size_mb * 8192 * _CONTAINER_OVERHEAD_RATIO) / duration
    video_kbps = int(total_kbps_budget - audio_kbps)

    min_viable_kbps = 100
    if video_kbps < min_viable_kbps:
        raise ValueError(
            "Target size is too small for this video's duration. "
            f"Try a target of at least "
            f"{_min_target_size_mb(duration, audio_kbps):.0f} MB."
        )

    return CompressionPlan(
        mode="target_size",
        target_size_mb=target_size_mb,
        video_bitrate_kbps=video_kbps,
    )


def _min_target_size_mb(duration_sec: float, audio_kbps: int) -> float:
    min_viable_kbps = 100
    total_kbps = min_viable_kbps + audio_kbps
    return (total_kbps * duration_sec) / (8192 * _CONTAINER_OVERHEAD_RATIO)


def _build_command(
    input_path: Path,
    output_path: Path,
    plan: CompressionPlan,
    info: VideoInfo,
    ffmpeg_bin: str,
) -> list[str]:
    cmd = [ffmpeg_bin, "-y", "-i", str(input_path)]

    # -map 0:v:0 -map 0:a:0? explicitly selects only the first video and
    # first audio stream (the '?' makes audio optional so files without
    # audio don't error). This avoids ffmpeg trying to mux subtitle or
    # data tracks from containers like MKV/MOV into MP4 which doesn't
    # support them, preventing "codec not currently supported in container"
    # errors.
    cmd += ["-map", "0:v:0", "-map", "0:a:0?"]

    # Cap resolution at 1080p on the long edge to help hit smaller targets
    # without a visible quality cliff. Only downscales, never upscales.
    # force_divisible_by=2 ensures both dimensions are even, which is
    # required by libx264 (and most other codecs).
    scale_filter = (
        "scale='min(1920,iw)':'min(1080,ih)'"
        ":force_original_aspect_ratio=decrease"
        ":force_divisible_by=2"
    )

    if plan.mode == "preset":
        assert plan.preset is not None
        cmd += [
            "-vf",
            scale_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            str(plan.preset.crf),
        ]
    else:  # target_size
        assert plan.video_bitrate_kbps is not None
        v_kbps = plan.video_bitrate_kbps
        bufsize = v_kbps * 2
        cmd += [
            "-vf",
            scale_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-b:v",
            f"{v_kbps}k",
            "-maxrate",
            f"{v_kbps}k",
            "-bufsize",
            f"{bufsize}k",
        ]

    if info.has_audio:
        cmd += ["-c:a", "aac", "-b:a", f"{_AUDIO_BITRATE_KBPS}k"]
    else:
        cmd += ["-an"]

    cmd += [
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]
    return cmd


_TIME_RE = re.compile(r"out_time_ms=(\d+)")
_TIME_US_RE = re.compile(r"out_time_us=(\d+)")


async def compress_video(
    input_path: Path,
    output_path: Path,
    plan: CompressionPlan,
    info: VideoInfo,
    ffmpeg_bin: str = "ffmpeg",
    on_progress: Optional[ProgressCallback] = None,
    timeout_sec: float = 3600.0,
) -> Path:
    """Run ffmpeg to compress `input_path` into `output_path` per `plan`.

    `on_progress` is invoked periodically with a float in [0, 1] representing
    encoding progress, derived from ffmpeg's `-progress` machine-readable
    output compared against the source duration.
    """
    cmd = _build_command(input_path, output_path, plan, info, ffmpeg_bin)
    logger.info("Running ffmpeg: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    duration_sec = max(info.duration_sec, 0.001)
    stderr_chunks: list[bytes] = []

    async def _read_stderr() -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            stderr_chunks.append(line)

    async def _read_progress() -> None:
        assert proc.stdout is not None
        last_reported = -1.0
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors="ignore").strip()
            match = _TIME_US_RE.match(text) or _TIME_RE.match(text)
            if match and on_progress is not None:
                microseconds = int(match.group(1))
                current_sec = microseconds / 1_000_000
                fraction = min(current_sec / duration_sec, 1.0)
                # Throttle callback frequency to avoid API flooding.
                if fraction - last_reported >= 0.02 or fraction >= 1.0:
                    last_reported = fraction
                    await on_progress(fraction)

    try:
        await asyncio.wait_for(
            asyncio.gather(_read_stderr(), _read_progress(), proc.wait()),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise CompressionError("ffmpeg timed out") from exc

    if proc.returncode != 0 or not output_path.exists():
        stderr_text = b"".join(stderr_chunks).decode(errors="ignore")
        raise CompressionError(
            f"ffmpeg failed (exit code {proc.returncode}):\n{stderr_text[-2000:]}"
        )

    if on_progress is not None:
        await on_progress(1.0)

    return output_path
