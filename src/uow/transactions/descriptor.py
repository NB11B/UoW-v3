"""Transaction descriptor for optimistic concurrency control (OCC)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from ..contracts import GuardOp, MutationOp, Route, SuccessorKind, UoW
from ..state import WorldState


@dataclass(frozen=True)
class TransactionDescriptor:
    """In-flight transaction envelope: X_i = (U_i, S_base, R_i, W_i, P_i, C_i).

    Records the base sequence version, read set, write set, coupled keys,
    read/write/coupled versions, and proposed state hash.
    """

    uow_id: str
    base_sequence: int
    read_set: Tuple[str, ...]
    read_versions: Mapping[str, int]
    write_set: Tuple[str, ...]
    write_versions: Mapping[str, int]
    proposed_state_hash: str
    coupled_set: Tuple[str, ...] = ()
    coupled_versions: Mapping[str, int] = ()
    status: str = "PROPOSED"


def infer_footprint(route: Route) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Infers read and write key sets from a contract Route."""
    reads: set[str] = set()
    writes: set[str] = set()

    # Inspect guard for read keys
    if route.guard.op != GuardOp.ALWAYS and route.guard.key is not None:
        reads.add(route.guard.key)

    # Inspect successor for dynamic read keys
    if route.successor.kind == SuccessorKind.FROM_ATTRIBUTE and route.successor.value is not None:
        reads.add(route.successor.value)

    # Inspect mutations for writes and potential reads (e.g. ADD/SUB reads before writing)
    for m in route.mutations:
        if m.key is not None:
            writes.add(m.key)
            if m.op in (MutationOp.ADD, MutationOp.SUB):
                reads.add(m.key)

    return tuple(sorted(reads)), tuple(sorted(writes))


def create_transaction_descriptor(
    uow: UoW,
    base_state: WorldState,
    *,
    read_set: Optional[Sequence[str]] = None,
    write_set: Optional[Sequence[str]] = None,
    version_key: str = "__versions__",
    coupling_key: str = "__couplings__",
) -> TransactionDescriptor:
    """Constructs a TransactionDescriptor from a UoW and a base WorldState.

    Explicitly snapshots versions for:
    1. read_set
    2. write_set
    3. coupled_set (keys coupled to any key in write_set)
    """
    _idx, route = uow.Gamma.select_route(base_state)

    inferred_reads, inferred_writes = infer_footprint(route)
    actual_reads = tuple(sorted(set(read_set if read_set is not None else inferred_reads)))
    actual_writes = tuple(sorted(set(write_set if write_set is not None else inferred_writes)))

    couplings_map = base_state.get(coupling_key, {})
    if not isinstance(couplings_map, Mapping):
        couplings_map = {}

    coupled_keys: set[str] = set()
    for w_key in actual_writes:
        for c_key in couplings_map.get(w_key, ()):
            coupled_keys.add(str(c_key))
    coupled_tuple = tuple(sorted(coupled_keys))

    versions_map = base_state.get(version_key, {})
    if not isinstance(versions_map, Mapping):
        versions_map = {}

    read_versions = {k: int(versions_map.get(k, 0)) for k in actual_reads}
    write_versions = {k: int(versions_map.get(k, 0)) for k in actual_writes}
    coupled_versions = {k: int(versions_map.get(k, 0)) for k in coupled_tuple}

    from ..engine import propose

    proposal = propose(uow, base_state)

    return TransactionDescriptor(
        uow_id=uow.H.identity,
        base_sequence=base_state.sequence,
        read_set=actual_reads,
        read_versions=read_versions,
        write_set=actual_writes,
        write_versions=write_versions,
        proposed_state_hash=proposal.proposed_state.state_hash,
        coupled_set=coupled_tuple,
        coupled_versions=coupled_versions,
        status="PROPOSED",
    )
