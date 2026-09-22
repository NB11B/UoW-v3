"""Saga orchestration, authoritative progress tracking, and reverse-order compensation for Pass 4.1."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, make_uow
from ..engine import CertificateResult, Proposal, certify, propose
from ..state import WorldState
from ..transactions import create_transaction_descriptor
from .descriptor import (
    CompensationSpec,
    EffectDescriptor,
    EffectReceipt,
    EffectStatus,
    compute_idempotency_key,
)
from .runner import (
    EFFECT_CELL,
    EffectRunner,
    ORCH_EFFECTS_KEY,
    get_effects_map,
)

ORCH_SAGAS_KEY = "__sagas__"
ORCH_COMPENSATION_FAILED_KEY = "__compensation_failed__"


class SagaStatus(str, Enum):
    """Lifecycle status for a multi-step distributed Saga."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"


@dataclass(frozen=True)
class SagaRecord:
    """Authoritative durable record of Saga execution progress stored in WorldState."""

    saga_id: str
    status: SagaStatus
    steps: Tuple[str, ...]
    current_step_index: int
    completed_effects: Tuple[str, ...]
    compensation_cursor: int
    compensated_effects: Tuple[str, ...]
    unresolved_effects: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "saga_id": self.saga_id,
            "status": self.status.value,
            "steps": list(self.steps),
            "current_step_index": self.current_step_index,
            "completed_effects": list(self.completed_effects),
            "compensation_cursor": self.compensation_cursor,
            "compensated_effects": list(self.compensated_effects),
            "unresolved_effects": list(self.unresolved_effects),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SagaRecord:
        return cls(
            saga_id=str(data["saga_id"]),
            status=SagaStatus(data["status"]),
            steps=tuple(data.get("steps", ())),
            current_step_index=int(data.get("current_step_index", 0)),
            completed_effects=tuple(data.get("completed_effects", ())),
            compensation_cursor=int(data.get("compensation_cursor", 0)),
            compensated_effects=tuple(data.get("compensated_effects", ())),
            unresolved_effects=tuple(data.get("unresolved_effects", ())),
        )


def get_sagas_map(state: WorldState) -> Dict[str, SagaRecord]:
    """Extracts all saga records from authoritative world state."""
    raw = state.attributes.get(ORCH_SAGAS_KEY, {})
    if not isinstance(raw, Mapping):
        return {}
    res = {}
    for k, v in raw.items():
        if isinstance(v, Mapping):
            res[str(k)] = SagaRecord.from_dict(v)
    return res


class SagaCompensationError(Exception):
    """Raised when one or more compensation actions fail, retaining unresolved state."""

    def __init__(self, message: str, unresolved_effects: List[EffectDescriptor]) -> None:
        super().__init__(message)
        self.unresolved_effects = unresolved_effects


@dataclass(frozen=True)
class SagaStep:
    """A single step in a multi-step Saga."""

    name: str
    build_effect: Callable[[WorldState], EffectDescriptor]


class SagaCoordinator:
    """Orchestrates multi-step distributed sagas with authoritative state and reverse-order compensation."""

    def __init__(self, runner: EffectRunner) -> None:
        self.runner = runner

    def get_saga(self, saga_id: str) -> Optional[SagaRecord]:
        """Retrieves saga progress record from authoritative WorldState."""
        return get_sagas_map(self.runner.sequencer.current_state).get(saga_id)

    def _commit_saga_record(self, record: SagaRecord) -> WorldState:
        """Atomically persists updated SagaRecord into authoritative WorldState with control-state preservation."""
        curr_state = self.runner.sequencer.current_state
        sagas = get_sagas_map(curr_state)
        sagas[record.saga_id] = record
        serialized = {k: v.to_dict() for k, v in sagas.items()}

        uow_id = f"saga::{record.saga_id}::{record.status.value}::{curr_state.sequence}"
        uow = make_uow(
            identity=uow_id,
            routes=[
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(Mutation(MutationOp.SET, ORCH_SAGAS_KEY, serialized),),
                    successor=Successor.preserve(),
                )
            ],
            matrix_cell=EFFECT_CELL,
            parent_context="sagas",
        )
        prop = propose(uow, curr_state)
        tx = create_transaction_descriptor(uow, curr_state, write_set=(ORCH_SAGAS_KEY,))
        cert = certify(uow, curr_state, prop)
        committed_state, _ = self.runner.sequencer.commit(uow, prop, tx, cert)
        return committed_state

    def _set_effect_status(
        self,
        effect: EffectDescriptor,
        new_status: EffectStatus,
        *,
        receipt: Optional[EffectReceipt] = None,
        compensation_effect_id: Optional[str] = None,
    ) -> EffectDescriptor:
        """Durably mutates effect status in WorldState preserving enclosing cursor and status."""
        curr_state = self.runner.sequencer.current_state
        eff_map = get_effects_map(curr_state)
        kwargs: Dict[str, Any] = {"status": new_status}
        if receipt is not None:
            kwargs["receipt"] = receipt
        if compensation_effect_id is not None:
            kwargs["compensation_effect_id"] = compensation_effect_id

        updated = replace(effect, **kwargs)
        eff_map[updated.effect_id] = updated
        serialized = {k: v.to_dict() for k, v in eff_map.items()}

        mutations = [Mutation(MutationOp.SET, ORCH_EFFECTS_KEY, serialized)]
        write_set = [ORCH_EFFECTS_KEY]

        if new_status == EffectStatus.COMPENSATION_FAILED:
            failed_list = list(curr_state.attributes.get(ORCH_COMPENSATION_FAILED_KEY, ()))
            failed_list.append(updated.to_dict())
            mutations.append(Mutation(MutationOp.SET, ORCH_COMPENSATION_FAILED_KEY, failed_list))
            write_set.append(ORCH_COMPENSATION_FAILED_KEY)

        uow_id = f"effect_status::{updated.effect_id}::{new_status.value}::{curr_state.sequence}"
        uow = make_uow(
            identity=uow_id,
            routes=[
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=tuple(mutations),
                    successor=Successor.preserve(),
                )
            ],
            matrix_cell=EFFECT_CELL,
            parent_context="effects",
        )
        prop = propose(uow, curr_state)
        tx = create_transaction_descriptor(uow, curr_state, write_set=tuple(write_set))
        cert = certify(uow, curr_state, prop)
        self.runner.sequencer.commit(uow, prop, tx, cert)
        return updated

    def execute_saga(
        self,
        steps: Sequence[SagaStep],
        *,
        saga_id: str = "default_saga",
    ) -> List[EffectDescriptor]:
        """Executes saga steps in forward order; on failure, triggers reverse compensation."""
        record = self.get_saga(saga_id)
        if record is not None and record.status == SagaStatus.COMPLETED:
            curr_map = get_effects_map(self.runner.sequencer.current_state)
            return [curr_map[eff_id] for eff_id in record.completed_effects if eff_id in curr_map]

        if record is None:
            record = SagaRecord(
                saga_id=saga_id,
                status=SagaStatus.RUNNING,
                steps=tuple(s.name for s in steps),
                current_step_index=0,
                completed_effects=(),
                compensation_cursor=0,
                compensated_effects=(),
                unresolved_effects=(),
            )
            self._commit_saga_record(record)

        executed: List[EffectDescriptor] = []
        curr_map = get_effects_map(self.runner.sequencer.current_state)
        for eff_id in record.completed_effects:
            if eff_id in curr_map:
                executed.append(curr_map[eff_id])

        for idx in range(record.current_step_index, len(steps)):
            step = steps[idx]
            try:
                curr_state = self.runner.sequencer.current_state
                effect = step.build_effect(curr_state)
                res = self.runner.execute_effect(effect)
                executed.append(res)

                record = replace(
                    record,
                    current_step_index=idx + 1,
                    completed_effects=tuple(record.completed_effects) + (res.effect_id,),
                )
                self._commit_saga_record(record)
            except Exception as exc:
                self.compensate(executed, saga_id=saga_id, root_cause=exc)
                raise exc

        record = replace(record, status=SagaStatus.COMPLETED)
        self._commit_saga_record(record)
        return executed

    def compensate(
        self,
        executed: Optional[Sequence[EffectDescriptor]] = None,
        *,
        saga_id: Optional[str] = None,
        root_cause: Optional[Exception] = None,
    ) -> List[EffectDescriptor]:
        """Compensates executed effects in strict reverse order [F_n, ..., F_1] using first-class child effects."""
        sid = saga_id or "default_saga"
        record = self.get_saga(sid)
        eff_map = get_effects_map(self.runner.sequencer.current_state)

        if record is None:
            comp_ids = tuple(e.effect_id for e in (executed or ()))
            record = SagaRecord(
                saga_id=sid,
                status=SagaStatus.COMPENSATING,
                steps=(),
                current_step_index=len(comp_ids),
                completed_effects=comp_ids,
                compensation_cursor=0,
                compensated_effects=(),
                unresolved_effects=(),
            )
            self._commit_saga_record(record)
        elif record.status not in (SagaStatus.COMPENSATING, SagaStatus.COMPENSATION_FAILED):
            record = replace(record, status=SagaStatus.COMPENSATING)
            self._commit_saga_record(record)

        existing_completed = list(record.completed_effects)
        if executed:
            for e in executed:
                if e.effect_id not in existing_completed:
                    existing_completed.append(e.effect_id)
        if tuple(existing_completed) != record.completed_effects:
            record = replace(record, completed_effects=tuple(existing_completed))
            self._commit_saga_record(record)

        all_completed = list(record.completed_effects)
        reversed_effects = list(reversed(all_completed))

        compensated_list: List[EffectDescriptor] = []
        unresolved: List[EffectDescriptor] = []

        for cursor_idx, eff_id in enumerate(reversed_effects):
            if eff_id in record.compensated_effects:
                if eff_id in eff_map:
                    compensated_list.append(eff_map[eff_id])
                continue

            curr_state = self.runner.sequencer.current_state
            eff_map = get_effects_map(curr_state)
            eff = eff_map.get(eff_id)
            if eff is None:
                continue

            if not eff.compensation:
                record = replace(
                    record,
                    compensation_cursor=cursor_idx,
                    compensated_effects=tuple(record.compensated_effects) + (eff_id,),
                )
                self._commit_saga_record(record)
                continue

            comp_spec = eff.compensation
            record = replace(record, compensation_cursor=cursor_idx)
            self._commit_saga_record(record)

            if eff.status != EffectStatus.COMPENSATING:
                eff = self._set_effect_status(eff, EffectStatus.COMPENSATING)

            comp_effect_id = f"comp::{eff.effect_id}"
            comp_effect = EffectDescriptor(
                effect_id=comp_effect_id,
                uow_id=f"{eff.uow_id}::comp",
                intent=comp_spec.intent,
                idempotency_key=comp_spec.idempotency_key,
                request=comp_spec.request,
                status=EffectStatus.INTENDED,
                pre_state_hash=eff.pre_state_hash,
            )

            try:
                comp_res = self.runner.execute_effect(comp_effect)
                eff_compensated = self._set_effect_status(
                    eff,
                    EffectStatus.COMPENSATED,
                    receipt=comp_res.receipt,
                    compensation_effect_id=comp_res.effect_id,
                )
                compensated_list.append(eff_compensated)

                record = replace(
                    record,
                    compensated_effects=tuple(record.compensated_effects) + (eff_id,),
                )
                self._commit_saga_record(record)

            except Exception as comp_err:
                failed_eff = self._set_effect_status(
                    eff,
                    EffectStatus.COMPENSATION_FAILED,
                )
                unresolved.append(failed_eff)

                record = replace(
                    record,
                    status=SagaStatus.COMPENSATION_FAILED,
                    unresolved_effects=tuple(record.unresolved_effects) + (eff_id,),
                )
                self._commit_saga_record(record)

        if unresolved:
            raise SagaCompensationError(
                f"Saga compensation failed for {len(unresolved)} effect(s). State retained.",
                unresolved_effects=unresolved,
            )

        record = replace(record, status=SagaStatus.COMPENSATED)
        self._commit_saga_record(record)
        return compensated_list
