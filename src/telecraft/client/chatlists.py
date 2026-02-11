from __future__ import annotations

from dataclasses import dataclass

from telecraft.tl.generated.types import InputChatlistDialogFilter


@dataclass(frozen=True, slots=True)
class ChatlistRef:
    filter_id: int

    @classmethod
    def by_filter(cls, filter_id: int) -> ChatlistRef:
        return cls(filter_id=int(filter_id))

    def to_input(self) -> InputChatlistDialogFilter:
        return InputChatlistDialogFilter(filter_id=int(self.filter_id))
