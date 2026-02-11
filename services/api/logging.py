from __future__ import annotations

import logging
import os
from typing import Any

from pythonjsonlogger import jsonlogger


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO")
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"levelname": "level", "name": "logger"},
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_event(logger: logging.Logger, msg: str, **fields: Any) -> None:
    if fields:
        logger.info(msg, extra=fields)
    else:
        logger.info(msg)
