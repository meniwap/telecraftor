from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from telecraft.bot.events import MessageEvent

Filter = Callable[[MessageEvent], bool]


def all_() -> Filter:
    return lambda _e: True


def text() -> Filter:
    return lambda e: e.text is not None and e.text != ""


def command(name: str) -> Filter:
    prefix = f"/{name}"

    def _f(e: MessageEvent) -> bool:
        t = e.text or ""
        # naive: '/cmd' or '/cmd@bot'
        if not t.startswith(prefix):
            return False
        if len(t) == len(prefix):
            return True
        nxt = t[len(prefix)]
        return nxt in {" ", "@", "\n", "\t"}

    return _f


@dataclass(frozen=True, slots=True)
class And:
    a: Filter
    b: Filter

    def __call__(self, e: MessageEvent) -> bool:
        return self.a(e) and self.b(e)


@dataclass(frozen=True, slots=True)
class Or:
    a: Filter
    b: Filter

    def __call__(self, e: MessageEvent) -> bool:
        return self.a(e) or self.b(e)


def and_(a: Filter, b: Filter) -> Filter:
    return And(a=a, b=b)


def or_(a: Filter, b: Filter) -> Filter:
    return Or(a=a, b=b)

