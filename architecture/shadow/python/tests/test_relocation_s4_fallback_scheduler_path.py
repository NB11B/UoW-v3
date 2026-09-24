from __future__ import annotations

import inspect

import uow
from uow.proposer import DeterministicFallbackScheduler
from uow.realizations.scheduling.fallback import (
    DeterministicFallbackScheduler as ImplDeterministicFallbackScheduler,
)


def test_s4_fallback_scheduler_imports_remain_identity_compatible():
    assert DeterministicFallbackScheduler is ImplDeterministicFallbackScheduler
    assert uow.DeterministicFallbackScheduler is ImplDeterministicFallbackScheduler


def test_s4_historical_fallback_scheduler_module_is_only_compatibility_shim():
    import uow.proposer.fallback as shim

    source = inspect.getsource(shim)
    assert "class DeterministicFallbackScheduler" not in source
    assert "def fallback_schedule(" not in source
    assert "realizations.scheduling.fallback" in source


def test_s4_fallback_realization_uses_relocated_resource_policy_directly():
    import uow.realizations.scheduling.fallback as implementation

    source = inspect.getsource(implementation)
    assert "from .resource_policies import" in source
    assert "from ...resources.policies import" not in source
