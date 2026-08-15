"""Persistent per-chat forum-topic restriction.

When a chat has a lock set, the bot only responds inside that one forum topic
(``message_thread_id``) in that chat — every other topic, including
"General", is ignored. Set/cleared via the ``/topic`` command
(``commands/handlers.py``). IDs persist to a JSON file (``TOPIC_LOCK_FILE``)
so the setting survives restarts; with no file configured the store is
in-memory only.
"""

import json
from pathlib import Path
from typing import Optional

from ..utils.logger import get_logger

logger = get_logger()


class TopicLockStore:
    """chat_id -> locked topic_id, optionally file-backed."""

    def __init__(self, path: str = ""):
        self._path: Optional[Path] = Path(path) if path else None
        self._locks: dict[int, int] = {}
        self._load()

    def _load(self) -> None:
        if not self._path or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._locks = {int(k): int(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error(f"Could not read topic-lock file {self._path}: {e}")

    def get(self, chat_id: int) -> Optional[int]:
        return self._locks.get(chat_id)

    def set(self, chat_id: int, topic_id: int) -> None:
        """Lock a chat to a single topic and persist."""
        if self._locks.get(chat_id) == topic_id:
            return
        self._locks[chat_id] = topic_id
        self._persist()
        logger.info("Topic lock set", chat_id=chat_id, topic_id=topic_id)

    def clear(self, chat_id: int) -> None:
        """Remove any topic restriction for a chat and persist."""
        if self._locks.pop(chat_id, None) is not None:
            self._persist()
            logger.info("Topic lock cleared", chat_id=chat_id)

    def _persist(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._locks), encoding="utf-8")
        except OSError as e:
            logger.error(f"Could not write topic-lock file {self._path}: {e}")


_topic_lock_store: Optional[TopicLockStore] = None


def get_topic_lock_store() -> TopicLockStore:
    """Get the global topic-lock store instance."""
    global _topic_lock_store
    if _topic_lock_store is None:
        from ..config import get_settings
        _topic_lock_store = TopicLockStore(get_settings().topic_lock_file)
    return _topic_lock_store
