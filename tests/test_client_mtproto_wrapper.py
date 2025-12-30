from __future__ import annotations

import asyncio

import pytest

from telecraft.client.mtproto import (
    ClientInit,
    MtprotoClient,
    MtprotoClientError,
    wrap_with_layer_init,
)
from telecraft.tl.generated.functions import HelpGetConfig, InitConnection, InvokeWithLayer


def test_wrap_with_layer_init_shape() -> None:
    init = ClientInit(api_id=12345, device_model="dev", system_version="sys", app_version="1.2.3")
    wrapped = wrap_with_layer_init(query=HelpGetConfig(), init=init)

    assert isinstance(wrapped, InvokeWithLayer)
    assert wrapped.layer > 0
    assert isinstance(wrapped.query, InitConnection)
    assert wrapped.query.api_id == 12345
    assert wrapped.query.device_model == "dev"
    assert wrapped.query.system_version == "sys"
    assert wrapped.query.app_version == "1.2.3"
    assert isinstance(wrapped.query.query, HelpGetConfig)


def test_client_invoke_with_layer_requires_init() -> None:
    c = MtprotoClient()
    with pytest.raises(MtprotoClientError):
        asyncio.run(c.invoke_with_layer(HelpGetConfig()))

