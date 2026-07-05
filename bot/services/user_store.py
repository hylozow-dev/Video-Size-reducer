"""Lightweight JSON-file-based store for user info and video requests."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from bot.config import settings

logger = logging.getLogger(__name__)

_STORE_FILENAME = "user_store.json"


def _store_path() -> Path:
    return settings.storage_dir / _STORE_FILENAME


def _load_store() -> dict[str, Any]:
    """Load the store from disk. Returns empty structure on any failure."""
    path = _store_path()
    if not path.exists():
        return {"users": {}, "requests": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "users" not in data:
            data["users"] = {}
        if "requests" not in data:
            data["requests"] = {}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load user store: %s", exc)
        return {"users": {}, "requests": {}}


def _save_store(data: dict[str, Any]) -> None:
    """Save the store to disk atomically (write to tmp then rename)."""
    path = _store_path()
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    except OSError as exc:
        logger.error("Failed to save user store: %s", exc)


def record_user(user_id: int, username: str | None, first_name: str | None) -> None:
    """Record or update a user in the store."""
    data = _load_store()
    uid_str = str(user_id)
    if uid_str not in data["users"]:
        data["users"][uid_str] = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "first_seen": time.time(),
        }
    else:
        # Update name info in case it changed
        data["users"][uid_str]["username"] = username
        data["users"][uid_str]["first_name"] = first_name
    _save_store(data)


def record_video_request(
    user_id: int, file_id: str, filename: str, file_size: int | None
) -> None:
    """Record a video request for a user."""
    data = _load_store()
    uid_str = str(user_id)
    if uid_str not in data["requests"]:
        data["requests"][uid_str] = []
    data["requests"][uid_str].append({
        "file_id": file_id,
        "filename": filename,
        "file_size": file_size,
        "timestamp": time.time(),
    })
    _save_store(data)


def get_all_users() -> list[dict[str, Any]]:
    """Return list of all users sorted by first_seen (newest first)."""
    data = _load_store()
    users = list(data["users"].values())
    users.sort(key=lambda u: u.get("first_seen", 0), reverse=True)
    return users


def get_user_requests(user_id: int) -> list[dict[str, Any]]:
    """Return all video requests for a given user, newest first."""
    data = _load_store()
    uid_str = str(user_id)
    requests = data["requests"].get(uid_str, [])
    # Return newest first
    return list(reversed(requests))
