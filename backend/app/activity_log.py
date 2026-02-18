"""In-memory activity log for URL operations (for display on frontend)."""
from datetime import datetime, timezone
from typing import List, Dict, Any

_MAX_ENTRIES = 100
_entries: List[Dict[str, Any]] = []


def add(entry: Dict[str, Any]) -> None:
    """Append an entry (ts added automatically)."""
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    _entries.append(row)
    while len(_entries) > _MAX_ENTRIES:
        _entries.pop(0)


def get(limit: int = 50) -> List[Dict[str, Any]]:
    """Return last `limit` entries, newest first."""
    out = _entries[-limit:]
    out.reverse()
    return out
