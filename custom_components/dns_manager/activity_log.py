"""In-memory activity log for diagnostics and troubleshooting."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

MAX_LOG_ENTRIES = 200


@dataclass(slots=True)
class ActivityLogEntry:
    timestamp: str
    level: str
    message: str
    details: dict[str, Any] | None = None


class DnsManagerActivityLog:
    """Ring buffer of recent integration events (included in diagnostics download)."""

    def __init__(self, max_entries: int = MAX_LOG_ENTRIES) -> None:
        self._entries: deque[ActivityLogEntry] = deque(maxlen=max_entries)

    def log(self, level: str, message: str, **details: Any) -> None:
        entry = ActivityLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            message=message,
            details=details or None,
        )
        self._entries.append(entry)

    def info(self, message: str, **details: Any) -> None:
        self.log("info", message, **details)

    def warning(self, message: str, **details: Any) -> None:
        self.log("warning", message, **details)

    def error(self, message: str, **details: Any) -> None:
        self.log("error", message, **details)

    def as_list(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in self._entries]
