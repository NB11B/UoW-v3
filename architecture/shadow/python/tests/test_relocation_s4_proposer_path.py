from __future__ import annotations

import inspect

import uow
from uow import (
    Guard,
    GuardOp,
    HeuristicSchedulingProposer,
    Mutation,
    MutationOp,
    ResourceRequirement,
    ResourceState,
    Route,
    create_initial_orchestration_state,
    make_resource_domain_task,
    set_authoritative_resource_state,
)
from uow.implementations.adaptation.runtime import (
    ProposerOrchestrationEngine as ImplEngine,
    run_proposer_orchestration as impl_run,
)
from uow.proposer import ProposerOrchestrationEngine, run_proposer_orchestration
from uow_shadow.proposer_reconstruction import run_proposer_orchestration_reconstructed


def _fixture():
    registry = {
        "A": make_resource_domain_task(
            "A",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))],
            ResourceRequirement(cpu_cores=1, ram_units=1, priority=1),
        ),
        "B": make_resource_domain_task(
            "B",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r1", 20),))],
            ResourceRequirement(cpu_cores=1, ram_units=1, priority=2),
        ),
    }
    base = create_initial_orchestration_state(
        ["A", "B"],
        {},
        attributes={"r0": 0, "r1": 0},
    )
    state = set_authoritative_resource_state(
        base,
        ResourceState(
            capacities={
                "cpu_cores": 4,
                "ram_units": 8,
                "gpu_slots": 0,
                "npu_slots": 0,
                "energy_budget": 100,
                "cost": 100,
            }
        ),
    )
    return registry, state


def _semantic_view(state):
    attrs = dict(state.attributes)
    attrs.pop("__versions__", None)
    return {
        "attributes": attrs,
        "cursor": state.cursor,
        "status": state.status,
        "sequence": state.sequence,
    }


class CrashingProposer:
    def model_id(self):
        return "crashing"

    def model_version(self):
        return "1"

    def propose(self, ready_candidates, graph, state):
        raise RuntimeError("simulated proposer crash")


def test_s4_proposer_import_paths_remain_identity_compatible():
    assert ProposerOrchestrationEngine is ImplEngine
    assert run_proposer_orchestration is impl_run
    assert uow.ProposerOrchestrationEngine is ImplEngine
    assert uow.run_proposer_orchestration is impl_run


def test_s4_historical_proposer_engine_is_only_shim():
    import uow.proposer.engine as shim

    source = inspect.getsource(shim)
    assert "class ProposerOrchestrationEngine" not in source
    assert "def run_proposer_orchestration" not in source
    assert "implementations.adaptation.runtime" in source


def test_s4_proposer_implementation_uses_common_application_spine():
    import uow.implementations.adaptation.runtime as implementation

    source = inspect.getsource(implementation)
    assert "DEFAULT_APPLICATION_SPINE.execute" in source
    assert "create_transaction_descriptor" not in source
    assert "seq.commit(" not in source
    assert "from ...engine import" not in source


def test_s4_proposer_runtime_preserves_reconstructed_u14_semantics():
    registry, initial = _fixture()

    moved_state, moved_seq, moved_telemetry = run_proposer_orchestration(
        registry,
        initial,
        HeuristicSchedulingProposer(),
    )
    reconstructed = run_proposer_orchestration_reconstructed(
        registry,
        initial,
        HeuristicSchedulingProposer(),
    )

    assert _semantic_view(moved_state) == _semantic_view(reconstructed.final_state)
    assert moved_state.status == "HALTED"
    assert moved_seq.ledger.verify_integrity()
    assert len(moved_telemetry) == len(reconstructed.telemetry)
    assert [t.certificate.fallback_triggered for t in moved_telemetry] == [
        t.certificate.fallback_triggered for t in reconstructed.telemetry
    ]


def test_s4_proposer_crash_still_falls_back_without_authority_leakage():
    registry, initial = _fixture()

    final_state, seq, telemetry = run_proposer_orchestration(
        registry,
        initial,
        CrashingProposer(),
    )

    assert final_state.status == "HALTED"
    assert final_state.get("r0") == 10
    assert final_state.get("r1") == 20
    assert seq.ledger.verify_integrity()
    assert telemetry
    assert any(t.certificate.fallback_triggered for t in telemetry)
