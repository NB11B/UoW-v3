from __future__ import annotations

from pathlib import Path
import sys

from uow import Guard, GuardOp, Mutation, MutationOp, Route, Successor, WorldState, make_uow
from uow_shadow.conformance_registry import DEFAULT_CONFORMANCE_REGISTRY as SHADOW_REGISTRY
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


def test_r7_parallel_facade_exposes_validated_seams_without_copying_logic():
    assert DEFAULT_APPLICATION_SPINE is SHADOW_SPINE
    assert DEFAULT_CONFORMANCE_REGISTRY is SHADOW_REGISTRY
    assert CursorPolicy is ShadowCursorPolicy


def test_r7_dual_layout_application_semantics_match():
    uow = _uow()
    state = WorldState(attributes={"x": 0}, cursor=uow.H.identity)

    via_shadow = SHADOW_SPINE.execute(
        uow,
        state,
        cursor_policy=ShadowCursorPolicy.OWNED,
    )
    via_facade = DEFAULT_APPLICATION_SPINE.execute(
        uow,
        state,
        cursor_policy=CursorPolicy.OWNED,
    )

    assert via_facade.state.state_hash == via_shadow.state.state_hash
    assert via_facade.state.to_dict() == via_shadow.state.to_dict()
    assert via_facade.conformance == via_shadow.conformance
    assert via_facade.authorization == via_shadow.authorization
    assert via_facade.evidence == via_shadow.evidence


def test_r7_dual_layout_conformance_manifest_matches():
    assert DEFAULT_CONFORMANCE_REGISTRY.manifest() == SHADOW_REGISTRY.manifest()
    assert len(DEFAULT_CONFORMANCE_REGISTRY.domains()) == 9


def test_r7_facade_does_not_replace_canonical_uow_import_surface():
    import uow

    assert not hasattr(uow, "uow_architecture_facade")
    assert "implementations.python" not in str(getattr(uow, "__file__", ""))
