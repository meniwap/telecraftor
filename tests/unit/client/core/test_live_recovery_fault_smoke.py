from __future__ import annotations

from types import SimpleNamespace

from tests.live.optional.test_live_unknown_constructor_recovery import (
    _GET_DIFFERENCE,
    _LAYER_BOOTSTRAP,
    _successful_recovery_call_kind,
)


def test_successful_recovery_call_kind__recognizes_only_exact_recovery_calls() -> None:
    bootstrap = SimpleNamespace(
        TL_NAME="invokeWithLayer",
        query=SimpleNamespace(
            TL_NAME="initConnection",
            query=SimpleNamespace(TL_NAME="help.getConfig"),
        ),
    )

    assert _successful_recovery_call_kind(bootstrap) == _LAYER_BOOTSTRAP
    assert (
        _successful_recovery_call_kind(SimpleNamespace(TL_NAME="updates.getDifference"))
        == _GET_DIFFERENCE
    )
    assert (
        _successful_recovery_call_kind(
            SimpleNamespace(
                TL_NAME="invokeWithLayer",
                query=SimpleNamespace(
                    TL_NAME="initConnection",
                    query=SimpleNamespace(TL_NAME="users.getUsers"),
                ),
            )
        )
        is None
    )
    assert _successful_recovery_call_kind(SimpleNamespace(TL_NAME="updates.getState")) is None
