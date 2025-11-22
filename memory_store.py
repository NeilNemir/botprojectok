"""In-memory staging storage for payment requests before approval.

Only approved payments are persisted in DB. New payment requests are staged here
until approver confirms. If the bot restarts, staged requests are lost (acceptable
per current requirements)."""

from typing import Dict, Any
from threading import RLock

_lock = RLock()
_store: Dict[int, Dict[str, Any]] = {}

def put_staged(temp_id: int, data: Dict[str, Any]) -> None:
    with _lock:
        _store[int(temp_id)] = dict(data)

def get_staged(temp_id: int) -> Dict[str, Any] | None:
    with _lock:
        return _store.get(int(temp_id))

def pop_staged(temp_id: int) -> Dict[str, Any] | None:
    with _lock:
        return _store.pop(int(temp_id), None)

def list_staged_ids() -> list[int]:
    with _lock:
        return list(_store.keys())

