"""Certified materialization of derived orchestration decisions into ordinary UoWs.

A materializer has no authority to mutate WorldState. It deterministically lowers a
state-derived decision into an ordinary UoW, which is independently re-materialized
and fingerprinted before the existing PROPOSE -> CERTIFY -> COMMIT path may execute it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..contracts import UoW
from ..state import WorldState, canonical_json
import hashlib


def canonical_uow_payload(uow: UoW) -> dict[str, Any]:
    """Return a stable, JSON-compatible representation of a UoW contract."""
    return {
        "H": {
            "identity": uow.H.identity,
            "source_category": uow.H.source_category.value,
            "target_category": uow.H.target_category.value,
            "layer": uow.H.layer,
            "parent_context": uow.H.parent_context,
        },
        "Gamma": [
            {
                "guard": {
                    "op": route.guard.op.value,
                    "key": route.guard.key,
                    "operand": route.guard.operand,
                },
                "mutations": [
                    {
                        "op": mutation.op.value,
                        "key": mutation.key,
                        "operand": mutation.operand,
                    }
                    for mutation in route.mutations
                ],
                "successor": {
                    "kind": route.successor.kind.value,
                    "value": route.successor.value,
                },
            }
            for route in uow.Gamma.routes
        ],
        "M": {"phase": uow.M.phase.value},
        "R": {"implementation": uow.R.implementation},
        "B": {
            "input_type": uow.B.input_type,
            "output_type": uow.B.output_type,
            "schema_version": uow.B.schema_version,
        },
        "E": {
            "verifier": uow.E.verifier,
            "require_hash_chain": uow.E.require_hash_chain,
        },
        "T": {
            "clock_owner": uow.T.clock_owner,
            "causal_epoch": uow.T.causal_epoch,
        },
    }


def uow_fingerprint(uow: UoW) -> str:
    """Cryptographic fingerprint of the complete canonical UoW representation."""
    raw = canonical_json(canonical_uow_payload(uow))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MaterializedUoW:
    """State-bound output of a deterministic derived-UoW materializer."""

    materializer_id: str
    pre_state_hash: str
    uow: UoW
    materialization_hash: str


class UoWMaterializer(Protocol):
    """Protocol for deterministic lowering of derived decisions to ordinary UoWs."""

    @property
    def materializer_id(self) -> str:
        ...

    def materialize(self, state: WorldState) -> MaterializedUoW:
        ...


def bind_materialization(
    materializer_id: str,
    state: WorldState,
    uow: UoW,
) -> MaterializedUoW:
    """Bind a generated UoW to the materializer identity and authoritative pre-state."""
    return MaterializedUoW(
        materializer_id=materializer_id,
        pre_state_hash=state.state_hash,
        uow=uow,
        materialization_hash=uow_fingerprint(uow),
    )


def certify_materialization(
    materializer: UoWMaterializer,
    state: WorldState,
    materialized: MaterializedUoW,
) -> bool:
    """Independently re-materialize and require exact canonical agreement."""
    if materialized.materializer_id != materializer.materializer_id:
        return False
    if materialized.pre_state_hash != state.state_hash:
        return False

    expected = materializer.materialize(state)
    if expected.materialization_hash != materialized.materialization_hash:
        return False
    if uow_fingerprint(materialized.uow) != materialized.materialization_hash:
        return False
    return canonical_uow_payload(expected.uow) == canonical_uow_payload(materialized.uow)
