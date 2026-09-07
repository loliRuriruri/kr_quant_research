"""Profile local files without collectors; write a new immutable audit result."""
import argparse
import json
from pathlib import Path

from kr_quant.research.pit_readiness import audit_local_sources
from kr_quant.research.selection_ledger import write_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Never allow an audit command to overwrite an existing result or source.
    if args.output.exists():
        parser.error("output already exists; use a new audit filename")
    result = audit_local_sources(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    saved = write_once(args.output, result)
    print(json.dumps(saved, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
