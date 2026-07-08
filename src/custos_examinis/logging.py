import logging
import re
from collections.abc import MutableMapping
from typing import Any, cast

import structlog

_SECRET_PATTERNS = [
    # Order matters: the bearer-token pattern must run before the generic
    # key/value pattern, otherwise "Authorization: Bearer xyz" gets partially
    # redacted at "Bearer" and leaves the actual token trailing behind it.
    re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password|authorization)(['\"]?\s*[:=]\s*['\"]?)([^\s'\"]+)"),
]

_REDACTED = "***REDACTED***"


def _redact_match(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 3:
        return match.group(1) + match.group(2) + _REDACTED
    return _REDACTED


def _redact_value(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(_redact_match, redacted)
    return redacted


def redact_secrets_processor(
    logger: object, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = _redact_value(value)
    return event_dict


def configure_logging(*, debug: bool) -> None:
    logging.basicConfig(
        format="%(message)s",
        level=logging.DEBUG if debug else logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_secrets_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
