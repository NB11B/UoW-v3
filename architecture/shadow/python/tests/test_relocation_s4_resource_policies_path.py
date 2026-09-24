from __future__ import annotations

import inspect

import uow
from uow.resources import (
    BaseSchedulingPolicy,
    CostEnergySchedulingPolicy,
    FIFOSchedulingPolicy,
    GreedyCapacitySchedulingPolicy,
    PriorityDeadlineSchedulingPolicy,
    filter_feasible_candidates,
)
from uow.realizations.scheduling.resource_policies import (
    BaseSchedulingPolicy as ImplBaseSchedulingPolicy,
    CostEnergySchedulingPolicy as ImplCostEnergySchedulingPolicy,
    FIFOSchedulingPolicy as ImplFIFOSchedulingPolicy,
    GreedyCapacitySchedulingPolicy as ImplGreedyCapacitySchedulingPolicy,
    PriorityDeadlineSchedulingPolicy as ImplPriorityDeadlineSchedulingPolicy,
    filter_feasible_candidates as impl_filter_feasible_candidates,
)


def test_s4_resource_policy_imports_remain_identity_compatible():
    assert BaseSchedulingPolicy is ImplBaseSchedulingPolicy
    assert CostEnergySchedulingPolicy is ImplCostEnergySchedulingPolicy
    assert FIFOSchedulingPolicy is ImplFIFOSchedulingPolicy
    assert GreedyCapacitySchedulingPolicy is ImplGreedyCapacitySchedulingPolicy
    assert PriorityDeadlineSchedulingPolicy is ImplPriorityDeadlineSchedulingPolicy
    assert filter_feasible_candidates is impl_filter_feasible_candidates

    assert uow.BaseSchedulingPolicy is ImplBaseSchedulingPolicy
    assert uow.CostEnergySchedulingPolicy is ImplCostEnergySchedulingPolicy
    assert uow.FIFOSchedulingPolicy is ImplFIFOSchedulingPolicy
    assert uow.GreedyCapacitySchedulingPolicy is ImplGreedyCapacitySchedulingPolicy
    assert uow.PriorityDeadlineSchedulingPolicy is ImplPriorityDeadlineSchedulingPolicy
    assert uow.filter_feasible_candidates is impl_filter_feasible_candidates


def test_s4_historical_resource_policies_module_is_only_compatibility_shim():
    import uow.resources.policies as shim

    source = inspect.getsource(shim)
    assert "class BaseSchedulingPolicy" not in source
    assert "class FIFOSchedulingPolicy" not in source
    assert "class GreedyCapacitySchedulingPolicy" not in source
    assert "class PriorityDeadlineSchedulingPolicy" not in source
    assert "class CostEnergySchedulingPolicy" not in source
    assert "def filter_feasible_candidates" not in source
    assert "realizations.scheduling.resource_policies" in source
