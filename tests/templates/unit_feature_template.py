"""
Template for onboarding a new V2 feature namespace in unit tests.

Usage:
1. Copy this file into tests/unit/client/v2/test_<feature>_contracts.py
2. Replace FEATURE_NAMESPACE and FEATURE_METHOD placeholders.
3. Add rows to tests/meta/v2_method_matrix.yaml before adding wrappers.
4. Keep names in format: test_<namespace>__<method>__<scenario>
"""

from __future__ import annotations

import pytest

FEATURE_NAMESPACE = "feature"
FEATURE_METHOD = "method"


@pytest.mark.unit
def test_feature__method__delegates_to_raw() -> None:
    pytest.skip("Replace with real contract test")


@pytest.mark.unit
def test_feature__method__forwards_args() -> None:
    pytest.skip("Replace with real contract test")


@pytest.mark.unit
def test_feature__method__handles_rpc_error() -> None:
    pytest.skip("Replace with real contract test")
