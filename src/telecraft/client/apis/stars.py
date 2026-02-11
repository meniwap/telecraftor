from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import (
    resolve_input_peer,
    resolve_input_peer_or_self,
    resolve_input_user,
)
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    PaymentsGetPaymentForm,
    PaymentsGetStarsGiftOptions,
    PaymentsGetStarsRevenueStats,
    PaymentsGetStarsStatus,
    PaymentsGetStarsTopupOptions,
    PaymentsGetStarsTransactions,
    PaymentsGetStarsTransactionsById,
    PaymentsSendStarsForm,
)
from telecraft.tl.generated.types import InputStarsTransaction

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class StarsTransactionsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(
        self,
        *,
        peer: PeerRef | str = "self",
        offset: str = "",
        limit: int = 100,
        inbound: bool = False,
        outbound: bool = False,
        ascending: bool = False,
        ton: bool = False,
        subscription_id: str | None = None,
        timeout: float = 20.0,
    ) -> Any:
        input_peer = await resolve_input_peer_or_self(self._raw, peer, timeout=timeout)

        flags = 0
        if inbound:
            flags |= 1
        if outbound:
            flags |= 2
        if ascending:
            flags |= 4
        if subscription_id is not None:
            flags |= 8
        if ton:
            flags |= 16

        return await self._raw.invoke_api(
            PaymentsGetStarsTransactions(
                flags=flags,
                inbound=True if inbound else None,
                outbound=True if outbound else None,
                ascending=True if ascending else None,
                ton=True if ton else None,
                subscription_id=subscription_id,
                peer=input_peer,
                offset=str(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def by_id(
        self,
        *,
        peer: PeerRef | str = "self",
        tx_ids: Sequence[str] = (),
        refund: bool = False,
        ton: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        if not tx_ids:
            raise ValueError("tx_ids cannot be empty")

        input_peer = await resolve_input_peer_or_self(self._raw, peer, timeout=timeout)
        transaction_flags = 1 if refund else 0
        input_ids = [
            InputStarsTransaction(
                flags=transaction_flags,
                refund=True if refund else None,
                id=str(tx_id),
            )
            for tx_id in tx_ids
        ]

        flags = 1 if ton else 0
        return await self._raw.invoke_api(
            PaymentsGetStarsTransactionsById(
                flags=flags,
                ton=True if ton else None,
                peer=input_peer,
                id=input_ids,
            ),
            timeout=timeout,
        )


class StarsRevenueAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def stats(
        self,
        peer: PeerRef,
        *,
        dark: bool = False,
        ton: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)

        flags = 0
        if dark:
            flags |= 1
        if ton:
            flags |= 2

        return await self._raw.invoke_api(
            PaymentsGetStarsRevenueStats(
                flags=flags,
                dark=True if dark else None,
                ton=True if ton else None,
                peer=input_peer,
            ),
            timeout=timeout,
        )


class StarsFormsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get(
        self,
        invoice: Any,
        *,
        theme_params: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if theme_params is not None else 0
        return await self._raw.invoke_api(
            PaymentsGetPaymentForm(
                flags=flags,
                invoice=invoice,
                theme_params=theme_params,
            ),
            timeout=timeout,
        )

    async def send(self, form_id: int, invoice: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PaymentsSendStarsForm(form_id=int(form_id), invoice=invoice),
            timeout=timeout,
        )


class StarsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.transactions = StarsTransactionsAPI(raw)
        self.revenue = StarsRevenueAPI(raw)
        self.forms = StarsFormsAPI(raw)

    async def status(
        self,
        *,
        peer: PeerRef | str = "self",
        ton: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        input_peer = await resolve_input_peer_or_self(self._raw, peer, timeout=timeout)
        flags = 1 if ton else 0
        return await self._raw.invoke_api(
            PaymentsGetStarsStatus(
                flags=flags,
                ton=True if ton else None,
                peer=input_peer,
            ),
            timeout=timeout,
        )

    async def topup_options(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(PaymentsGetStarsTopupOptions(), timeout=timeout)

    async def gift_options(self, *, user: PeerRef | None = None, timeout: float = 20.0) -> Any:
        if user is None:
            flags = 0
            input_user = None
        else:
            flags = 1
            input_user = await resolve_input_user(self._raw, user, timeout=timeout)

        return await self._raw.invoke_api(
            PaymentsGetStarsGiftOptions(
                flags=flags,
                user_id=input_user,
            ),
            timeout=timeout,
        )
