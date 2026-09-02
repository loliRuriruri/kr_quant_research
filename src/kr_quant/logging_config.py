from __future__ import annotations

import logging
import re
from pathlib import Path


class SensitiveDataFilter(logging.Filter):
    """Redact sensitive API keys, secrets, and authorization tokens from logs."""

    _KEY_VAL_PAT = re.compile(
        r"(?i)(AUTH_KEY|api[-_]?key|app[-_]?key|app[-_]?secret|secret[-_]?key|bot[-_]?token|client[-_]?secret)\s*[:=]\s*([^\s&,;]+)"
    )
    _BEARER_PAT = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9_\-\.]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = self._KEY_VAL_PAT.sub(r"\1=***REDACTED***", record.msg)
            msg = self._BEARER_PAT.sub(r"\1***REDACTED***", msg)
            record.msg = msg
        return True


def setup_logging(log_dir: Path, run_id: str | None = None, level: int = logging.INFO) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("kr_quant")
    logger.setLevel(level)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    redactor = SensitiveDataFilter()

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    stream.addFilter(redactor)
    logger.addHandler(stream)

    name = f"{run_id or 'screener'}.log"
    file_handler = logging.FileHandler(log_dir / name, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redactor)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger
