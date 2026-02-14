from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PremiumBoostSlots:
    slots: tuple[int, ...]

    @classmethod
    def of(cls, *slots: int) -> PremiumBoostSlots:
        return cls(slots=tuple(int(item) for item in slots))

    @classmethod
    def from_sequence(cls, slots: Sequence[int]) -> PremiumBoostSlots:
        return cls(slots=tuple(int(item) for item in slots))


def build_premium_slots(slots: PremiumBoostSlots | Sequence[int] | None) -> list[int] | None:
    if slots is None:
        return None
    if isinstance(slots, PremiumBoostSlots):
        return [int(item) for item in slots.slots]
    return [int(item) for item in slots]
