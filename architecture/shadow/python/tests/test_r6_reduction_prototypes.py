from __future__ import annotations

import inspect

import pytest

from uow.compat.v2 import Guard, GuardOp, Mutation, MutationOp, Route, Successor, WorldState, make_uow
from uow.engine import propose

from uow_shadow.authority_protocol import QuorumAuthorityProvider, submit_via_authority_provider
from uow_shadow.distributed_authority_reconstruction import make_shadow_authority_cluster
from uow_shadow.spine import ApplicationSpine, CursorPolicy


def _uow(identity: str, key: str = "x"):
    return make_uow(
        identity,
        [
            Route(
                Guard(GuardOp.ALWAYS),
                (Mutation(MutationOp.ADD, key, 1),),
                Successor.preserve(),
            )
        ],
    )


def test_r6_common_application_spine_preserves_cursor_owned_execution():
    spine = ApplicationSpine()
    uow = _uow("owned")
    state = WorldState(attributes={"x": 0}, cursor="owned", status="RUNNING")

    result = spine.execute(uow, state, cursor_policy=CursorPolicy.OWNED)

    assert result.state.get("x") == 1
    assert result.state.cursor == "owned"
    assert result.state.sequence == 1
    assert result.conformance.accepted
    assert result.evidence.authorization_reference == result.authorization.authorization_id


def test_r6_common_application_spine_preserves_detached_control_plane_execution():
    spine = ApplicationSpine()
    bookkeeping = _uow("bookkeeping", key="audit")
    state = WorldState(
        attributes={"audit": 0},
        cursor="workflow-task",
        status="RUNNING",
    )

    with pytest.raises(ValueError, match="Cursor-owned application"):
        spine.execute(bookkeeping, state, cursor_policy=CursorPolicy.OWNED)

    result = spine.execute(
        bookkeeping,
        state,
        cursor_policy=CursorPolicy.DETACHED,
    )
    assert result.state.get("audit") == 1
    assert result.state.cursor == "workflow-task"
    assert result.state.sequence == 1


def test_r6_reconstruction_helper_now_delegates_authority_flow_to_spine():
    import uow_shadow.reconstruction as reconstruction

    source = inspect.getsource(reconstruction)
    assert "DEFAULT_APPLICATION_SPINE.execute" in source
    assert "core_certify_adapter" not in source
    assert "apply_authorized_transition" not in source


def test_r6_shadow_distributed_authority_satisfies_provider_protocol():
    initial = WorldState(
        attributes={"counter": 0},
        cursor="dist.increment",
        status="RUNNING",
    )
    provider = make_shadow_authority_cluster(initial)
    assert isinstance(provider, QuorumAuthorityProvider)

    uow = _uow("dist.increment", key="counter")
    proposal = propose(uow, provider.nodes["A"].state)
    committed, authorization, votes, results = submit_via_authority_provider(
        provider,
        uow,
        proposal,
    )

    assert committed
    assert authorization is not None
    assert len(votes) == 3
    assert len(authorization.voters) >= 2
    assert all(r.applied for r in results.values())


def test_r6_authority_protocol_and_shadow_provider_do_not_import_qualification_package():
    import ast
    import uow_shadow.authority_protocol as protocol
    import uow_shadow.distributed_authority_reconstruction as provider

    def imported_modules(module):
        tree = ast.parse(inspect.getsource(module))
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
        return tuple(names)

    for module in (protocol, provider):
        assert not any(
            name.startswith("qualification.distributed_authority")
            for name in imported_modules(module)
        )
