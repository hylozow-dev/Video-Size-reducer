"""Small formatting helpers used across handlers."""
from __future__ import annotations


def human_size(size_bytes: float) -> str:
    """Format a byte count as a human-readable string (e.g. '12.3 MB')."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"  # unreachable, keeps type checkers happy


def human_duration(seconds: float) -> str:
    """Format a duration in seconds as 'HH:MM:SS' or 'MM:SS'."""
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def progress_bar(fraction: float, length: int = 20) -> str:
    """Render a simple text progress bar, e.g. '[########------------] 40%'."""
    fraction = max(0.0, min(fraction, 1.0))
    filled = int(round(length * fraction))
    bar = "#" * filled + "-" * (length - filled)
    return f"[{bar}] {int(round(fraction * 100))}%"


def reduction_percent(original_bytes: int, new_bytes: int) -> float:
    """Return the percentage size reduction (0-100). 0 if no reduction/growth."""
    if original_bytes <= 0:
        return 0.0
    reduction = (original_bytes - new_bytes) / original_bytes * 100
    return max(reduction, 0.0)
