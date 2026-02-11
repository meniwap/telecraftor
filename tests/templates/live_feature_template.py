"""
Template for onboarding a new live feature lane test.

Usage:
1. Copy into tests/live/core|second_account|optional/ as needed.
2. Keep naming format: test_<namespace>__<method>__<scenario>
3. Emit audit logs via audit_reporter and write local artifacts via finalize_run.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.live]


def test_feature__method__roundtrip_live() -> None:
    pytest.skip("Replace with real live flow")


def test_feature__method__cleanup_on_failure() -> None:
    pytest.skip("Replace with real cleanup verification")
