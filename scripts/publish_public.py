# -*- coding: utf-8 -*-
"""CLI: rebuild dist-public and deploy to Cloudflare Pages."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from kr_quant.web.publish import publish_public_snapshot  # noqa: E402


def main() -> int:
    result = publish_public_snapshot(deploy=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
