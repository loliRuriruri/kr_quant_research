"""Read-only CLI for production recent filing reconciliation."""
import json
import sys
from kr_quant.ingest.recent_filings import check

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(check(), ensure_ascii=False, indent=2))
