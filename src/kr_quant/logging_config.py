from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_dir: Path, run_id: str | None = None, level: int = logging.INFO) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("kr_quant")
    logger.setLevel(level)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    name = f"{run_id or 'screener'}.log"
    file_handler = logging.FileHandler(log_dir / name, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger
