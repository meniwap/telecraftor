from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import MessagesAppendTodoList, MessagesToggleTodoCompleted
from telecraft.tl.generated.types import TodoItem, TodoList

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


def _build_todo_items(items: Sequence[str | TodoItem | Any]) -> list[Any]:
    out: list[Any] = []
    for idx, item in enumerate(items, start=1):
        if isinstance(item, TodoItem):
            out.append(item)
            continue
        if isinstance(item, str):
            out.append(TodoItem(id=idx, title=item))
            continue
        out.append(item)
    return out


class TodosAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def append(
        self,
        peer: PeerRef,
        msg_id: int,
        items: Sequence[str | TodoItem | Any] = (),
        *,
        title: str = "",
        others_can_append: bool = False,
        others_can_complete: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if others_can_append:
            flags |= 1
        if others_can_complete:
            flags |= 2
        todo_list = TodoList(
            flags=flags,
            others_can_append=True if others_can_append else None,
            others_can_complete=True if others_can_complete else None,
            title=str(title),
            list=_build_todo_items(items),
        )
        return await self._raw.invoke_api(
            MessagesAppendTodoList(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
                list=todo_list,
            ),
            timeout=timeout,
        )

    async def toggle(
        self,
        peer: PeerRef,
        msg_id: int,
        item_ids: Sequence[int],
        *,
        completed: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        completed_ids = [int(x) for x in item_ids] if completed else []
        incompleted_ids = [] if completed else [int(x) for x in item_ids]
        return await self._raw.invoke_api(
            MessagesToggleTodoCompleted(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
                completed=completed_ids,
                incompleted=incompleted_ids,
            ),
            timeout=timeout,
        )

    async def complete(
        self,
        peer: PeerRef,
        msg_id: int,
        item_ids: Sequence[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.toggle(
            peer,
            msg_id,
            item_ids,
            completed=True,
            timeout=timeout,
        )

    async def uncomplete(
        self,
        peer: PeerRef,
        msg_id: int,
        item_ids: Sequence[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.toggle(
            peer,
            msg_id,
            item_ids,
            completed=False,
            timeout=timeout,
        )
