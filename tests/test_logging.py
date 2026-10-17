import io
import json
import logging

from trackfolio.logging_setup import JsonFormatter


def test_json_formatter_emits_only_allowed_fields_and_exceptions() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("trackfolio.test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info(
        "request", extra={"method": "GET", "path": "/", "status": 200, "ms": 3, "secret": "x"}
    )
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed")

    first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    assert first["method"] == "GET" and first["status"] == 200 and first["ms"] == 3
    assert "secret" not in first and "query" not in first
    assert second["level"] == "ERROR" and "ValueError: boom" in second["exc"]
