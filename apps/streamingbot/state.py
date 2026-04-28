from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class OffsetState:
    next_update_id: int | None = None


class OffsetStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load(self) -> OffsetState:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return OffsetState()
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return OffsetState()
        if not isinstance(decoded, dict):
            return OffsetState()
        value = decoded.get("next_update_id")
        if value is None:
            return OffsetState()
        try:
            return OffsetState(next_update_id=int(value))
        except (TypeError, ValueError):
            return OffsetState()

    def save(self, state: OffsetState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"next_update_id": state.next_update_id}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
