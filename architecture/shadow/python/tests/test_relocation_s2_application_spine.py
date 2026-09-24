from __future__ import annotations

import inspect
from pathlib import Path
import sys

from uow import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Route,
    Successor,
    create_initial_orchestration_state,
    make_domain_task,
)
from uow.application import DEFAULT_APPLICATION_SPINE as PRODUCTION_SPINE
from uow.orchestration.runtime import run_orchestration
from uow_shadow.reconstruction import run_orchestration_reconstructed


def _diamond():
    dependencies = {
        "A": (),
        "B": ("A",),
        "C": ("A",),
        "D": ("B", "C"),
    }
    tasks = {
        "A": make_domain_task(
            "A",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))],
        ),
        "B": make_domain_task(
            "B",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 20),))],
        ),
        "C": make_domain_task(
            "C",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r1", 30),))],
        ),
        "D": make_domain_task(
            "D",
            [
                Route(
                    Guard(GuardOp.ALWAYS),
                    (
                        Mutation(MutationOp.ADD, "r0", 5),
                        Mutation(MutationOp.ADD, "r1", 5),
                    ),
                )
            ],
        ),
    }
    return dependencies, tasks


def test_s2_orchestration_runtime_uses_common_application_spine():
    import uow.orchestration.runtime as runtime

    source = inspect.getsource(runtime)
    assert "DEFAULT_APPLICATION_SPINE.execute" in source
    assert "propose(" not in source
    assert "certify(" not in source
    assert "create_transaction_descriptor(" not in source
    assert "sequencer.commit(" not in source


def test_s2_orchestration_runtime_matches_reconstructed_u11_oracle():
    dependencies, tasks = _diamond()
    initial = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )

    canonical_state, canonical_seq = run_orchestration(tasks, initial)
    reconstructed = run_orchestration_reconstructed(tasks, initial)

    assert canonical_state.to_dict() == reconstructed.final_state.to_dict()
    assert canonical_state.state_hash == reconstructed.final_state.state_hash
    assert canonical_state.sequence == 13
    assert canonical_seq.ledger.verify_chain()


def test_s2_target_layout_facade_points_to_production_spine():
    repo = Path(__file__).resolve().parents[4]
    facade_root = repo / "implementations" / "python"
    if str(facade_root) not in sys.path:
        sys.path.insert(0, str(facade_root))

    from uow_architecture_facade.application import DEFAULT_APPLICATION_SPINE

    assert DEFAULT_APPLICATION_SPINE is PRODUCTION_SPINE
