from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Replaced by lane-specific suites: "
        "tests/live/core, tests/live/second_account, tests/live/optional"
    )
)


def test_live_migration__aggressive_suite__deprecated() -> None:
    pass
