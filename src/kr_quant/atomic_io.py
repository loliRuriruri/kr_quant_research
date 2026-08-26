from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pyarrow.parquet as pq


def write_parquet_atomic(frame: pd.DataFrame, path: Path, *, index: bool = False) -> None:
    """Write and validate a sibling parquet file before atomically replacing the target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        frame.to_parquet(temporary, index=index)
        with pq.ParquetFile(temporary) as parquet:
            metadata = parquet.metadata
            if metadata is None or metadata.num_rows != len(frame):
                raise IOError(
                    f"parquet validation failed for {path}: expected_rows={len(frame)} "
                    f"actual_rows={None if metadata is None else metadata.num_rows}"
                )
            if not index and parquet.schema_arrow.names != [str(column) for column in frame.columns]:
                raise IOError(f"parquet schema validation failed for {path}")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
