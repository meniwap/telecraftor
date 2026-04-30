from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.group_bot import _parse_args, main  # noqa: E402

if __name__ == "__main__":
    parsed = _parse_args()
    if parsed.config == "apps/bot_config.example.json":
        parsed.config = str(Path(__file__).with_name("bot_config.example.json"))
    try:
        asyncio.run(main(parsed))
    except KeyboardInterrupt:
        pass
