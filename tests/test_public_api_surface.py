"""Tests for UoW v3 Physical API Minimalism and Surface Conformance."""
from __future__ import annotations

import uow


def test_root_api_is_physically_minimal() -> None:
    """The root `uow` package must export ONLY 10 symbols."""
    expected_exports = {
        "UoW",
        "WorldState",
        "execute",
        "authority",
        "runtime",
        "autonomy",
        "semantic",
        "economics",
        "protocol",
        "adapters",
    }
    assert set(uow.__all__) == expected_exports, f"Unexpected exports in __all__: {set(uow.__all__) ^ expected_exports}"
    for sym in expected_exports:
        assert hasattr(uow, sym), f"Expected symbol '{sym}' missing from uow root"


def test_legacy_symbols_not_exported_from_root() -> None:
    """Legacy v2 symbols must NOT be exported from the root `uow` namespace."""
    legacy_symbols = [
        "Guard",
        "GuardOp",
        "Mutation",
        "MutationOp",
        "Route",
        "Successor",
        "SuccessorKind",
        "Timing",
        "make_uow",
        "Boundary",
        "Contract",
        "EvidenceSpec",
        "Header",
        "Lifecycle",
        "LifecyclePhase",
        "Realization",
        "CertificateResult",
        "EvidenceLedger",
        "EvidenceRecord",
        "Proposal",
        "commit",
        "certify",
        "execute_one",
        "propose",
        "run",
        "validate_graph",
        "ALL_MATRIX_CELLS",
        "MatrixCell",
        "WorkCategory",
        "DeterministicSequencer",
        "WALSequencer",
        "CommitSequencer",
        "TransactionConflictError",
        "TransactionDescriptor",
        "FIFOSchedulingPolicy",
        "CostEnergySchedulingPolicy",
        "BaseSchedulingPolicy",
        "GreedyCapacitySchedulingPolicy",
        "PriorityDeadlineSchedulingPolicy",
        "ResourceLease",
        "ResourceRequirement",
        "ResourceState",
        "EffectDescriptor",
        "EffectReceipt",
        "EffectRunner",
        "EffectStatus",
        "SagaCoordinator",
        "AdaptiveProposer",
        "BaseProposer",
        "DeterministicFallbackScheduler",
        "ModelIdentity",
        "ModelProposal",
        "PortableAdaptiveProposer",
        "ProposerOrchestrationEngine",
        "QuorumCommitSequencer",
        "RealizationGraph",
        "RealizationNode",
        "ActorBinding",
        "ActorDescriptor",
        "AdaptiveCompositionRuntime",
        "AuthoritativeHistory",
        "DurableWAL",
        "WireEnvelope",
    ]
    for sym in legacy_symbols:
        assert not hasattr(uow, sym), f"Legacy symbol '{sym}' leaked into root uow namespace!"


def test_compat_v2_exports_legacy_symbols() -> None:
    """`uow.compat.v2` must export legacy symbols for backward compatibility."""
    import uow.compat.v2 as v2

    expected_compat_symbols = [
        "UoW",
        "WorldState",
        "execute",
        "make_uow",
        "Guard",
        "GuardOp",
        "Mutation",
        "MutationOp",
        "Route",
        "Successor",
        "DeterministicSequencer",
        "RealizationGraph",
        "EvidenceLedger",
        "Proposal",
        "commit",
        "certify",
        "propose",
        "run",
        "FIFOSchedulingPolicy",
        "CostEnergySchedulingPolicy",
        "AdaptiveProposer",
        "SagaCoordinator",
    ]
    for sym in expected_compat_symbols:
        assert hasattr(v2, sym), f"Expected legacy symbol '{sym}' missing from uow.compat.v2"


def test_minimal_root_execution() -> None:
    """The root minimal API execute and WorldState can run a UoW."""
    from uow import WorldState, execute
    from uow.compat.v2 import Guard, GuardOp, Mutation, MutationOp, Route, make_uow

    initial_state = WorldState({"count": 0})
    work_unit = make_uow(
        identity="minimal_root_test_001",
        routes=[
            Route(
                guard=Guard(GuardOp.EQ, "count", 0),
                mutations=(Mutation(MutationOp.SET, "count", 1),),
            )
        ],
    )
    result_state, ledger = execute(work_unit, initial_state)
    assert result_state.get("count") == 1
    assert len(ledger.records) == 1
    assert ledger.records[0].uow_id == "minimal_root_test_001"
