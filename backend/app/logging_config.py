"""Logging setup so our diagnostics are actually visible on the host.

Under uvicorn/Gunicorn the root logger isn't configured for app loggers, so a plain
`logging.getLogger("tearsheet").info(...)` is dropped (only WARNING+ reaches the default
"last resort" handler). That's why Alpaca status lines never showed up in the Render logs.

`setup_logging()` attaches a single stdout StreamHandler to the "tearsheet" logger at INFO and
turns off propagation so lines aren't duplicated by uvicorn's handlers. Idempotent — safe to call
from both the web entrypoint (app/main.py) and the standalone prefetch cron (scripts/prefetch.py).
"""

from __future__ import annotations

import logging
import sys

_LOGGER_NAME = "tearsheet"


def setup_logging() -> logging.Logger:
    log = logging.getLogger(_LOGGER_NAME)
    if any(getattr(h, "_tearsheet", False) for h in log.handlers):
        return log  # already configured
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                                            datefmt="%H:%M:%S"))
    handler._tearsheet = True  # type: ignore[attr-defined]  # marker for idempotency
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False  # our handler already prints; don't double-log via root/uvicorn
    return log
