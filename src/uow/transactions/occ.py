"""Pure mathematical OCC hazard detection and atomic transaction mutation."""
from __future__ import annotations

from dataclasses import replace
from enum import Enum
from typing import Mapping, Optional, Tuple

from ..contracts import UoW
from ..engine import CertificateResult, Proposal
from ..state import WorldState, _thaw
from .descriptor import TransactionDescriptor


class HazardType(str, Enum):
    READ_WRITE_HAZARD = "READ_WRITE_HAZARD"
    WRITE_WRITE_HAZARD = "WRITE_WRITE_HAZARD"
    HIDDEN_COUPLING_HAZARD = "HIDDEN_COUPLING_HAZARD"


class TransactionConflictError(Exception):
    """Raised when an in-flight transaction fails OCC validation due to a data hazard."""

    def __init__(self, uow_id: str, hazard_type: HazardType, details: str) -> None:
        super().__init__(f"Transaction conflict on '{uow_id}' [{hazard_type.value}]: {details}")
        self.uow_id = uow_id
        self.hazard_type = hazard_type
        self.details = details


def validate_occ(
    current_state: WorldState,
    tx: TransactionDescriptor,
    *,
    version_key: str = "__versions__",
    coupling_key: str = "__couplings__",
) -> Tuple[bool, Optional[HazardType], Optional[str]]:
    """Purely validates a transaction against current authoritative state using OCC.

    Checks:
    1. Hidden State Coupling check: Did another transaction modify an invariant-coupled key?
    2. Read/Write Hazard (stale read): Did another transaction commit a write to any key in tx.read_set?
    3. Write/Write Hazard (lost update): Did another transaction commit a write to any key in tx.write_set?

    Returns: (is_valid, hazard_type, details)
    """
    versions_map = current_state.get(version_key, {})
    if not isinstance(versions_map, Mapping):
        versions_map = {}

    couplings_map = current_state.get(coupling_key, {})
    if not isinstance(couplings_map, Mapping):
        couplings_map = {}

    # 1. Hidden State Coupling check
    for w_key in tx.write_set:
        coupled_keys = couplings_map.get(w_key, ())
        if isinstance(coupled_keys, (list, tuple)):
            for c_key in coupled_keys:
                c_key_str = str(c_key)
                curr_c_ver = int(versions_map.get(c_key_str, 0))
                # Check snapshot version recorded in coupled_versions, falling back to read_versions
                base_c_ver = int(
                    tx.coupled_versions.get(
                        c_key_str,
                        tx.read_versions.get(c_key_str, tx.write_versions.get(c_key_str, 0)),
                    )
                )
                if curr_c_ver > base_c_ver:
                    return (
                        False,
                        HazardType.HIDDEN_COUPLING_HAZARD,
                        f"Coupled invariant violated: '{w_key}' is coupled to '{c_key_str}' which evolved concurrently",
                    )

    # 2. Read/Write Hazard check (stale read)
    for key in tx.read_set:
        curr_ver = int(versions_map.get(key, 0))
        base_ver = int(tx.read_versions.get(key, 0))
        if curr_ver > base_ver:
            return (
                False,
                HazardType.READ_WRITE_HAZARD,
                f"State key '{key}' was modified by a concurrent commit (base ver {base_ver} < current ver {curr_ver})",
            )

    # 3. Write/Write Hazard check (lost update)
    for key in tx.write_set:
        curr_ver = int(versions_map.get(key, 0))
        base_ver = int(tx.write_versions.get(key, 0))
        if curr_ver > base_ver:
            return (
                False,
                HazardType.WRITE_WRITE_HAZARD,
                f"Concurrent update conflict on target '{key}' (base ver {base_ver} < current ver {curr_ver})",
            )

    return True, None, None


def apply_transaction(
    current_state: WorldState,
    proposal: Proposal,
    tx: TransactionDescriptor,
    *,
    version_key: str = "__versions__",
) -> WorldState:
    """Applies transaction writes and updates version vectors atomically.

    Mutates only keys declared in tx.write_set (projected from proposed state),
    increments their versions, advances sequence, and updates cursor.
    """
    new_attrs = _thaw(current_state.attributes)

    versions_map = dict(new_attrs.get(version_key, {}))
    for key in tx.write_set:
        if key in proposal.proposed_state.attributes:
            new_attrs[key] = proposal.proposed_state.attributes[key]
        else:
            new_attrs.pop(key, None)
        versions_map[key] = versions_map.get(key, 0) + 1

    new_attrs[version_key] = versions_map

    new_cursor = proposal.selected_successor
    new_status = proposal.proposed_state.status

    return replace(
        current_state,
        attributes=new_attrs,
        cursor=new_cursor,
        status=new_status,
        sequence=current_state.sequence + 1,
        state_hash="",
    )
