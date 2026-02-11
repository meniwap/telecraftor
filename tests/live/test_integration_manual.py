from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Legacy manual integration module is deprecated. "
        "Use lane suites under tests/live/core, tests/live/second_account, tests/live/optional."
    )
)


def test_live_migration__integration_manual__deprecated() -> None:
    pass
