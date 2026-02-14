from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.types import InputInvoiceMessage, StarsAmount

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


@dataclass(frozen=True, slots=True)
class InvoiceRef:
    peer: PeerRef
    msg_id: int

    @classmethod
    def by_message(cls, peer: PeerRef, msg_id: int) -> InvoiceRef:
        return cls(peer=peer, msg_id=int(msg_id))


@dataclass(frozen=True, slots=True)
class StarsAmountRef:
    amount: int
    nanos: int = 0

    def to_tl(self) -> StarsAmount:
        return StarsAmount(amount=int(self.amount), nanos=int(self.nanos))


async def build_input_invoice(raw: MtprotoClient, ref_or_invoice: Any, *, timeout: float) -> Any:
    if isinstance(ref_or_invoice, InvoiceRef):
        return InputInvoiceMessage(
            peer=await resolve_input_peer(raw, ref_or_invoice.peer, timeout=timeout),
            msg_id=int(ref_or_invoice.msg_id),
        )

    if isinstance(ref_or_invoice, tuple) and len(ref_or_invoice) == 2:
        peer, msg_id = ref_or_invoice
        return InputInvoiceMessage(
            peer=await resolve_input_peer(raw, peer, timeout=timeout),
            msg_id=int(msg_id),
        )

    if isinstance(ref_or_invoice, dict) and {"peer", "msg_id"}.issubset(ref_or_invoice):
        return InputInvoiceMessage(
            peer=await resolve_input_peer(raw, ref_or_invoice["peer"], timeout=timeout),
            msg_id=int(ref_or_invoice["msg_id"]),
        )

    return ref_or_invoice
