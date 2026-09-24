from __future__ import annotations

import inspect

import uow
from uow.proposer import HeuristicSchedulingProposer, ReferenceSchedulingProposer
from uow.realizations.scheduling.heuristic import (
    HeuristicSchedulingProposer as ImplHeuristicSchedulingProposer,
    ReferenceSchedulingProposer as ImplReferenceSchedulingProposer,
)


def test_s4_heuristic_proposer_imports_remain_identity_compatible():
    assert HeuristicSchedulingProposer is ImplHeuristicSchedulingProposer
    assert ReferenceSchedulingProposer is ImplReferenceSchedulingProposer
    assert uow.HeuristicSchedulingProposer is ImplHeuristicSchedulingProposer
    assert uow.ReferenceSchedulingProposer is ImplReferenceSchedulingProposer


def test_s4_historical_heuristic_proposer_module_is_only_compatibility_shim():
    import uow.proposer.heuristic as shim

    source = inspect.getsource(shim)
    assert "class HeuristicSchedulingProposer" not in source
    assert "def propose(" not in source
    assert "realizations.scheduling.heuristic" in source
