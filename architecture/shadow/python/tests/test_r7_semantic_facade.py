from __future__ import annotations

from pathlib import Path
import sys

from uow import Guard, GuardOp, Mutation, MutationOp, Route, Successor, WorldState, make_uow
from uow.conformance import DEFAULT_CONFORMANCE_REGISTRY as PRODUCTION_REGISTRY
from uow_shadow.conformance_registry import DEFAULT_CONFORMANCE_REGISTRY as SHADOW_REGISTRY
from uow.application import DEFAULT_APPLICATION_SPINE as PRODUCTION_SPINE
from uow.application import CursorPolicy as ProductionCursorPolicy
from uow_shadow.spine import DEFAULT_APPLICATION_SPINE as SHADOW_SPINE
from uow_shadow.spine import CursorPolicy as ShadowCursorPolicy


REPO = Path(__file__).resolve().parents[4]
FACADE_ROOT = REPO / "implementations" / "python"
if str(FACADE_ROOT) not in sys.path:
    sys.path.insert(0, str(FACADE_ROOT))

from uow_architecture_facade import (  # noqa: E402
    DEFAULT_APPLICATION_SPINE,
    DEFAULT_CONFORMANCE_REGISTRY,
    CursorPolicy,
)


def _uow():
    return make_uow(
        "r7-facade-task",
        [
            Route(
                Guard(GuardOp.ALWAYS),
                (Mutation(MutationOp.SET, "x", 7),),
                Successor.halt(),
            )
        ],
    )


def test_r7_parallel_facade_exposes_production_application_seam_and_validated_conformance():
    assert DEFAULT_APPLICATION_SPINE is PRODUCTION_SPINE
    assert DEFAULT_CONFORMANCE_REGISTRY is PRODUCTION_REGISTRY
    assert CursorPolicy is ProductionCursorPolicy


def test_r7_dual_layout_application_semantics_match():
    uow = _uow()
    state = WorldState(attributes={"x": 0}, cursor=uow.H.identity)

    from uow.transactions import DeterministicSequencer

    via_shadow = SHADOW_SPINE.execute(
        uow,
        state,
        cursor_policy=ShadowCursorPolicy.OWNED,
    )
    via_facade = DEFAULT_APPLICATION_SPINE.execute(
        uow,
        DeterministicSequencer(state),
        cursor_policy=CursorPolicy.OWNED,
    )

    facade_attrs = dict(via_facade.state.attributes)
    facade_attrs.pop("__versions__", None)
    assert facade_attrs == dict(via_shadow.state.attributes)
    assert via_facade.state.cursor == via_shadow.state.cursor
    assert via_facade.state.status == via_shadow.state.status
    assert via_facade.state.sequence == via_shadow.state.sequence
    assert via_facade.state.get("x") == via_shadow.state.get("x") == 7


def test_r7_dual_layout_conformance_manifest_matches():
    assert DEFAULT_CONFORMANCE_REGISTRY.manifest() == SHADOW_REGISTRY.manifest()
    assert len(DEFAULT_CONFORMANCE_REGISTRY.domains()) == 9


def test_r7_facade_does_not_replace_canonical_uow_import_surface():
    import uow

    assert not hasattr(uow, "uow_architecture_facade")
    assert "implementations.python" not in str(getattr(uow, "__file__", ""))
