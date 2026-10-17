"""JSON-line logging to stdout.

Only operational fields are logged (method, path without query string, status, duration),
never request bodies, query strings or financial values.
"""

import json
import logging
import sys
from datetime import UTC, datetime

_EXTRA_FIELDS = ("method", "path", "status", "ms")


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _EXTRA_FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Send all logs to stdout as JSON; idempotent. Uvicorn's access log is replaced."""
    root = logging.getLogger()
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = True
