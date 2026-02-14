from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer, resolve_input_user
from telecraft.client.payments import build_input_invoice
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    PaymentsApplyGiftCode,
    PaymentsCheckGiftCode,
    PaymentsExportInvoice,
    PaymentsGetPaymentForm,
    PaymentsGetPaymentReceipt,
    PaymentsRefundStarsCharge,
    PaymentsSendPaymentForm,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class PaymentsFormsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get(self, form_id_msg_id_or_invoice: Any, *, timeout: float = 20.0) -> Any:
        invoice = await build_input_invoice(
            self._raw,
            form_id_msg_id_or_invoice,
            timeout=timeout,
        )
        return await self._raw.invoke_api(
            PaymentsGetPaymentForm(
                flags=0,
                invoice=invoice,
                theme_params=None,
            ),
            timeout=timeout,
        )

    async def send(
        self,
        form_id: int,
        invoice: Any,
        *,
        requested_info_id: str | None = None,
        shipping_option_id: str | None = None,
        credentials: Any | None = None,
        tip_amount: int | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if requested_info_id is not None:
            flags |= 1
        if shipping_option_id is not None:
            flags |= 2
        if tip_amount is not None:
            flags |= 4
        return await self._raw.invoke_api(
            PaymentsSendPaymentForm(
                flags=flags,
                form_id=int(form_id),
                invoice=await build_input_invoice(self._raw, invoice, timeout=timeout),
                requested_info_id=requested_info_id,
                shipping_option_id=shipping_option_id,
                credentials=credentials,
                tip_amount=int(tip_amount) if tip_amount is not None else None,
            ),
            timeout=timeout,
        )

    async def receipt(self, peer: PeerRef, msg_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PaymentsGetPaymentReceipt(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
            ),
            timeout=timeout,
        )


class PaymentsInvoiceAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def export_link(self, invoice_media: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PaymentsExportInvoice(invoice_media=invoice_media),
            timeout=timeout,
        )


class PaymentsGiftCodesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def check(self, slug: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(PaymentsCheckGiftCode(slug=str(slug)), timeout=timeout)

    async def apply(self, slug: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(PaymentsApplyGiftCode(slug=str(slug)), timeout=timeout)


class PaymentsStarsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def refund_charge(
        self,
        user: PeerRef,
        charge_id: str,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PaymentsRefundStarsCharge(
                user_id=await resolve_input_user(self._raw, user, timeout=timeout),
                charge_id=str(charge_id),
            ),
            timeout=timeout,
        )


class PaymentsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.forms = PaymentsFormsAPI(raw)
        self.invoice = PaymentsInvoiceAPI(raw)
        self.gift_codes = PaymentsGiftCodesAPI(raw)
        self.stars = PaymentsStarsAPI(raw)
