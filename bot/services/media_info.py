"""ffprobe wrapper used to inspect input video files before compression."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class ProbeError(RuntimeError):
    """Raised when ffprobe fails or returns unusable data."""


@dataclass(slots=True)
class VideoInfo:
    duration_sec: float
    width: int | None
    height: int | None
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool
    bit_rate: int | None
    size_bytes: int

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


async def probe_video(path: Path, ffprobe_bin: str = "ffprobe") -> VideoInfo:
    """Run ffprobe on `path` and return structured metadata.

    Raises ProbeError if the file cannot be analyzed (e.g. it's not a valid
    video, or ffprobe is missing).
    """
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise ProbeError(
            f"ffprobe exited with code {proc.returncode}: {stderr.decode(errors='ignore')}"
        )

    try:
        data = json.loads(stdout.decode(errors="ignore"))
    except json.JSONDecodeError as exc:
        raise ProbeError(f"Could not parse ffprobe output: {exc}") from exc

    fmt = data.get("format", {})
    streams = data.get("streams", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video_stream is None:
        raise ProbeError("No video stream found in the provided file")

    duration_raw = fmt.get("duration") or video_stream.get("duration")
    try:
        duration_sec = float(duration_raw) if duration_raw is not None else 0.0
    except (TypeError, ValueError):
        duration_sec = 0.0

    bit_rate_raw = fmt.get("bit_rate")
    try:
        bit_rate = int(bit_rate_raw) if bit_rate_raw is not None else None
    except (TypeError, ValueError):
        bit_rate = None

    return VideoInfo(
        duration_sec=duration_sec,
        width=video_stream.get("width"),
        height=video_stream.get("height"),
        video_codec=video_stream.get("codec_name"),
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
        has_audio=audio_stream is not None,
        bit_rate=bit_rate,
        size_bytes=path.stat().st_size,
    )
