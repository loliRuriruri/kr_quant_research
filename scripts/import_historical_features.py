"""Import/check saved feature inputs; write a new gap ledger, no collection."""
import argparse
from pathlib import Path

from kr_quant.research.feature_import import import_feature_cases
from kr_quant.research.selection_ledger import write_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--ticker", action="append", required=True)
    parser.add_argument("--decision", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new ledger filename")
    result = import_feature_cases(args.root.resolve(), tickers=args.ticker,
                                  decisions=args.decision, archive=args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_once(args.output, result)
    print({k: result[k] for k in ("status", "case_count", "blocked_count", "selected_count", "reason_counts")})
    for source in result["sources"]:
        print(source)


if __name__ == "__main__":
    main()
