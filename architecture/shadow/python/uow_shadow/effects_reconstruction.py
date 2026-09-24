"""R4 Q1 external-effects and saga reconstruction.

Internal authority transitions use the minimal shadow UoW authority path.
External invocation/reconciliation remains an explicit non-closure boundary.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from uow.contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, make_uow
from uow.effects.certification import (
    PrefixReceiptAuthenticator,
    ReceiptAuthenticator,
    verify_effect_intent_binding,
    verify_effect_receipt_binding,
)
from uow.effects.descriptor import EffectDescriptor, EffectReceipt, EffectStatus
from uow.effects.runner import EFFECT_CELL, ExternalClientProtocol, ORCH_EFFECTS_KEY, get_effects_map
from uow.effects.saga import (
    ORCH_COMPENSATION_FAILED_KEY,
    ORCH_SAGAS_KEY,
    SagaCompensationError,
    SagaRecord,
    SagaStatus,
    SagaStep,
    get_sagas_map,
)
from uow.state import WorldState

from .identity import shadow_identity
from .reconstruction import execute_explicit_uow_reconstructed
from .types import EvidenceEntryRef


class ShadowEffectRuntime:
    def __init__(
        self,
        initial_state: WorldState,
        client: ExternalClientProtocol,
        *,
        authenticator: Optional[ReceiptAuthenticator] = None,
        expected_signer: Optional[str] = "test-signer",
    ) -> None:
        self.state = initial_state
        self.client = client
        self.authenticator = authenticator or (
            PrefixReceiptAuthenticator(expected_signer) if expected_signer else None
        )
        self.evidence: List[EvidenceEntryRef] = []

    def evidence_root(self) -> str:
        return shadow_identity(
            "q1-shadow-evidence-root",
            tuple(e.entry_identity for e in self.evidence),
        )

    def _commit_effect_map(self, uow_id: str, effect_map: Mapping[str, EffectDescriptor]) -> None:
        serialized = {k: v.to_dict() for k, v in effect_map.items()}
        uow = make_uow(
            uow_id,
            [
                Route(
                    Guard(GuardOp.ALWAYS),
                    (Mutation(MutationOp.SET, ORCH_EFFECTS_KEY, serialized),),
                    Successor.preserve(),
                )
            ],
            matrix_cell=EFFECT_CELL,
            parent_context="effects-shadow-reconstruction",
        )
        self.state, entry = execute_explicit_uow_reconstructed(uow, self.state)
        self.evidence.append(entry)

    def _commit_saga_record(self, record: SagaRecord) -> None:
        sagas = get_sagas_map(self.state)
        sagas[record.saga_id] = record
        serialized = {k: v.to_dict() for k, v in sagas.items()}
        uow = make_uow(
            f"saga::{record.saga_id}::{record.status.value}::{self.state.sequence}",
            [
                Route(
                    Guard(GuardOp.ALWAYS),
                    (Mutation(MutationOp.SET, ORCH_SAGAS_KEY, serialized),),
                    Successor.preserve(),
                )
            ],
            matrix_cell=EFFECT_CELL,
            parent_context="sagas-shadow-reconstruction",
        )
        self.state, entry = execute_explicit_uow_reconstructed(uow, self.state)
        self.evidence.append(entry)

    def commit_intent(self, effect: EffectDescriptor) -> EffectDescriptor:
        current = get_effects_map(self.state)
        existing = current.get(effect.effect_id)
        if existing is not None:
            if existing.idempotency_key != effect.idempotency_key or existing.request != effect.request:
                raise ValueError("Cannot reuse effect_id with different request or idempotency key.")
            if existing.status in (EffectStatus.COMMITTED_INTENT, EffectStatus.PENDING_EXTERNAL):
                return existing
            if existing.status == EffectStatus.COMMITTED_RESULT:
                return existing

        verify_effect_intent_binding(self.state, effect)
        committed = replace(effect, status=EffectStatus.COMMITTED_INTENT)
        current[committed.effect_id] = committed
        self._commit_effect_map(f"intent::{effect.effect_id}", current)
        return committed

    def suspend_pending_external(self, effect: EffectDescriptor) -> EffectDescriptor:
        current = get_effects_map(self.state)
        existing = current.get(effect.effect_id)
        if existing is None:
            raise ValueError("Cannot suspend uncommitted effect.")
        if existing.status != EffectStatus.COMMITTED_INTENT:
            raise ValueError(f"Cannot suspend effect from status {existing.status.value!r}.")
        pending = replace(existing, status=EffectStatus.PENDING_EXTERNAL)
        current[pending.effect_id] = pending
        self._commit_effect_map(f"suspend::{effect.effect_id}", current)
        return pending

    def commit_receipt(self, effect: EffectDescriptor, receipt: EffectReceipt) -> EffectDescriptor:
        current = get_effects_map(self.state)
        existing = current.get(effect.effect_id)
        if existing is None:
            raise ValueError("Cannot commit receipt without previously committed authoritative intent.")
        if existing.status not in (EffectStatus.COMMITTED_INTENT, EffectStatus.PENDING_EXTERNAL):
            raise ValueError(f"Cannot commit receipt from status {existing.status.value!r}.")

        verify_effect_receipt_binding(
            existing,
            receipt,
            authenticator=self.authenticator,
        )
        result = replace(
            existing,
            status=EffectStatus.COMMITTED_RESULT,
            observation=receipt.response_payload,
            receipt=receipt,
        )
        current[result.effect_id] = result
        self._commit_effect_map(f"result::{effect.effect_id}", current)
        return result

    def execute_effect(self, effect: EffectDescriptor) -> EffectDescriptor:
        current = get_effects_map(self.state)
        existing = current.get(effect.effect_id)
        if existing is not None and existing.status == EffectStatus.COMMITTED_RESULT:
            return existing

        active = (
            existing
            if existing is not None
            and existing.status in (EffectStatus.COMMITTED_INTENT, EffectStatus.PENDING_EXTERNAL)
            else self.commit_intent(effect)
        )

        receipt = self.client.reconcile(active.idempotency_key)
        if receipt is None:
            request = dict(active.request)
            request["effect_id"] = active.effect_id
            if active.effect_id.startswith("comp::") or active.request.get("is_compensation"):
                request["is_compensation"] = True
            receipt = self.client.invoke(request, active.idempotency_key)

        return self.commit_receipt(active, receipt)

    def set_effect_status(
        self,
        effect: EffectDescriptor,
        status: EffectStatus,
        *,
        receipt: Optional[EffectReceipt] = None,
        compensation_effect_id: Optional[str] = None,
    ) -> EffectDescriptor:
        current = get_effects_map(self.state)
        kwargs: dict[str, Any] = {"status": status}
        if receipt is not None:
            kwargs["receipt"] = receipt
        if compensation_effect_id is not None:
            kwargs["compensation_effect_id"] = compensation_effect_id
        updated = replace(effect, **kwargs)
        current[updated.effect_id] = updated

        serialized = {k: v.to_dict() for k, v in current.items()}
        mutations = [Mutation(MutationOp.SET, ORCH_EFFECTS_KEY, serialized)]
        if status == EffectStatus.COMPENSATION_FAILED:
            failed = list(self.state.get(ORCH_COMPENSATION_FAILED_KEY, ()))
            failed.append(updated.to_dict())
            mutations.append(Mutation(MutationOp.SET, ORCH_COMPENSATION_FAILED_KEY, failed))

        uow = make_uow(
            f"effect-status::{updated.effect_id}::{status.value}::{self.state.sequence}",
            [Route(Guard(GuardOp.ALWAYS), tuple(mutations), Successor.preserve())],
            matrix_cell=EFFECT_CELL,
            parent_context="effects-shadow-reconstruction",
        )
        self.state, entry = execute_explicit_uow_reconstructed(uow, self.state)
        self.evidence.append(entry)
        return updated


class ShadowSagaCoordinator:
    def __init__(self, runtime: ShadowEffectRuntime) -> None:
        self.runtime = runtime

    def get_saga(self, saga_id: str) -> Optional[SagaRecord]:
        return get_sagas_map(self.runtime.state).get(saga_id)

    def execute_saga(
        self,
        steps: Sequence[SagaStep],
        *,
        saga_id: str = "default_saga",
    ) -> List[EffectDescriptor]:
        record = self.get_saga(saga_id)
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
            self.runtime._commit_saga_record(record)

        executed: List[EffectDescriptor] = []
        for index in range(record.current_step_index, len(steps)):
            try:
                effect = steps[index].build_effect(self.runtime.state)
                result = self.runtime.execute_effect(effect)
                executed.append(result)
                record = replace(
                    record,
                    current_step_index=index + 1,
                    completed_effects=tuple(record.completed_effects) + (result.effect_id,),
                )
                self.runtime._commit_saga_record(record)
            except Exception:
                self.compensate(executed, saga_id=saga_id)
                raise

        record = replace(record, status=SagaStatus.COMPLETED)
        self.runtime._commit_saga_record(record)
        return executed

    def compensate(
        self,
        completed: Sequence[EffectDescriptor],
        *,
        saga_id: str,
    ) -> List[EffectDescriptor]:
        record = self.get_saga(saga_id)
        if record is None:
            record = SagaRecord(
                saga_id=saga_id,
                status=SagaStatus.COMPENSATING,
                steps=(),
                current_step_index=0,
                completed_effects=tuple(e.effect_id for e in completed),
                compensation_cursor=0,
                compensated_effects=(),
                unresolved_effects=(),
            )
        else:
            record = replace(record, status=SagaStatus.COMPENSATING)
        self.runtime._commit_saga_record(record)

        compensated: List[EffectDescriptor] = []
        unresolved: List[EffectDescriptor] = []

        for effect in reversed(tuple(completed)):
            spec = effect.compensation
            if spec is None:
                continue
            effect = self.runtime.set_effect_status(effect, EffectStatus.COMPENSATING)
            comp_effect = EffectDescriptor(
                effect_id=f"comp::{effect.effect_id}",
                uow_id=f"{effect.uow_id}::comp",
                intent=spec.intent,
                idempotency_key=spec.idempotency_key,
                request=spec.request,
                status=EffectStatus.INTENDED,
                pre_state_hash=effect.pre_state_hash,
            )
            try:
                comp_result = self.runtime.execute_effect(comp_effect)
                updated = self.runtime.set_effect_status(
                    effect,
                    EffectStatus.COMPENSATED,
                    receipt=comp_result.receipt,
                    compensation_effect_id=comp_result.effect_id,
                )
                compensated.append(updated)
                record = replace(
                    record,
                    compensated_effects=tuple(record.compensated_effects) + (effect.effect_id,),
                )
                self.runtime._commit_saga_record(record)
            except Exception:
                failed = self.runtime.set_effect_status(effect, EffectStatus.COMPENSATION_FAILED)
                unresolved.append(failed)
                record = replace(
                    record,
                    status=SagaStatus.COMPENSATION_FAILED,
                    unresolved_effects=tuple(record.unresolved_effects) + (effect.effect_id,),
                )
                self.runtime._commit_saga_record(record)

        if unresolved:
            raise SagaCompensationError(
                f"Saga compensation failed for {len(unresolved)} effect(s). State retained.",
                unresolved,
            )

        record = replace(record, status=SagaStatus.COMPENSATED)
        self.runtime._commit_saga_record(record)
        return compensated
