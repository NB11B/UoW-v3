"""Execution runtime, idempotency reconciler, and external client protocols for Pass 4."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import time
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Tuple

from ..contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, make_uow
from ..engine import CertificateResult, Proposal, certify, propose
from ..ontology import MatrixCell, WorkCategory
from ..state import WorldState, canonical_json
from ..transactions import CommitSequencer, create_transaction_descriptor
from .certification import verify_effect_intent_binding, verify_effect_receipt_binding
from .descriptor import EffectDescriptor, EffectReceipt, EffectStatus, compute_idempotency_key

ORCH_EFFECTS_KEY = "__effects__"
EFFECT_CELL = MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA)


class ExternalClientProtocol(Protocol):
    """Abstract protocol for external world service clients."""

    def invoke(self, request: Mapping[str, Any], idempotency_key: str) -> EffectReceipt:
        """Invokes external service with deterministic idempotency token."""
        ...

    def reconcile(self, idempotency_key: str) -> Optional[EffectReceipt]:
        """Queries external service to check if an invocation already succeeded."""
        ...


class MockExternalClient:
    """Deterministic mock external client supporting idempotency, simulated crashes, and verification."""

    def __init__(self, signer_id: Optional[str] = "test-signer") -> None:
        self.signer_id = signer_id
        self.invocation_count = 0
        self.reconcile_count = 0
        self._executed_by_idemp: Dict[str, EffectReceipt] = {}
        self.crash_on_invoke = False
        self.fail_compensation = False

    def invoke(self, request: Mapping[str, Any], idempotency_key: str) -> EffectReceipt:
        self.invocation_count += 1
        if self.crash_on_invoke:
            raise ConnectionError("Simulated network crash during invocation")

        if idempotency_key in self._executed_by_idemp:
            # Idempotent deduplication: return existing receipt without side effects
            return self._executed_by_idemp[idempotency_key]

        payload = {"status": "SUCCESS", "echo": dict(request)}
        resp_hash = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        receipt_id = f"rcpt::{idempotency_key[:16]}"
        sig = f"sig::{self.signer_id}::{resp_hash[:16]}" if self.signer_id else None

        receipt = EffectReceipt(
            receipt_id=receipt_id,
            effect_id=str(request.get("effect_id", f"eff::{idempotency_key[:16]}")),
            idempotency_key=idempotency_key,
            response_payload=payload,
            response_hash=resp_hash,
            timestamp=str(int(time.time())),
            signature=sig,
        )
        self._executed_by_idemp[idempotency_key] = receipt
        return receipt

    def reconcile(self, idempotency_key: str) -> Optional[EffectReceipt]:
        self.reconcile_count += 1
        return self._executed_by_idemp.get(idempotency_key)


def get_effects_map(state: WorldState) -> Dict[str, EffectDescriptor]:
    raw = state.attributes.get(ORCH_EFFECTS_KEY, {})
    if not isinstance(raw, Mapping):
        return {}
    res = {}
    for k, v in raw.items():
        if isinstance(v, Mapping):
            res[str(k)] = EffectDescriptor.from_dict(v)
    return res


class EffectRunner:
    """Executes the 6-stage durable external effect lifecycle."""

    def __init__(
        self,
        sequencer: CommitSequencer,
        client: ExternalClientProtocol,
        *,
        expected_signer: Optional[str] = "test-signer",
    ) -> None:
        self.sequencer = sequencer
        self.client = client
        self.expected_signer = expected_signer

    def commit_intent(self, effect: EffectDescriptor) -> EffectDescriptor:
        """Stage 1 & 2: Certifies and durably commits effect intent."""
        curr_state = self.sequencer.current_state
        verify_effect_intent_binding(curr_state, effect)

        eff_committed = replace(effect, status=EffectStatus.COMMITTED_INTENT)
        current_map = get_effects_map(curr_state)
        current_map[eff_committed.effect_id] = eff_committed
        serialized_map = {k: v.to_dict() for k, v in current_map.items()}

        uow_id = f"intent::{effect.effect_id}"
        uow = make_uow(
            identity=uow_id,
            routes=[
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(Mutation(MutationOp.SET, ORCH_EFFECTS_KEY, serialized_map),),
                    successor=Successor.halt(),
                )
            ],
            matrix_cell=EFFECT_CELL,
            parent_context="effects",
        )

        prop = propose(uow, curr_state)
        tx = create_transaction_descriptor(uow, curr_state, write_set=(ORCH_EFFECTS_KEY,))
        cert = certify(uow, curr_state, prop)

        self.sequencer.commit(uow, prop, tx, cert)
        return eff_committed

    def execute_effect(self, effect: EffectDescriptor) -> EffectDescriptor:
        """Executes full lifecycle: commit_intent -> invoke/reconcile -> certify_receipt -> commit_result."""
        curr_map = get_effects_map(self.sequencer.current_state)
        existing = curr_map.get(effect.effect_id)

        # Replay / Idempotence Invariant: if already committed result, return immediately without network
        if existing and existing.status == EffectStatus.COMMITTED_RESULT:
            return existing

        # Stage 1 & 2: Commit intent if not already committed
        eff = existing if existing and existing.status in (
            EffectStatus.COMMITTED_INTENT,
            EffectStatus.PENDING_EXTERNAL,
        ) else self.commit_intent(effect)

        # Stage 3: Invoke or Reconcile
        receipt = self.client.reconcile(eff.idempotency_key)
        if receipt is None:
            req_with_id = dict(eff.request)
            req_with_id["effect_id"] = eff.effect_id
            receipt = self.client.invoke(req_with_id, eff.idempotency_key)

        # Stage 4 & 5: Certify Receipt
        verify_effect_receipt_binding(eff, receipt, expected_signer=self.expected_signer)

        # Stage 6: Commit Effect Result
        return self.commit_receipt(eff, receipt)

    def suspend_pending_external(self, effect: EffectDescriptor) -> EffectDescriptor:
        """Transitions an effect into PENDING_EXTERNAL for asynchronous/long-running operations."""
        curr_state = self.sequencer.current_state
        eff_pending = replace(effect, status=EffectStatus.PENDING_EXTERNAL)

        current_map = get_effects_map(curr_state)
        current_map[eff_pending.effect_id] = eff_pending
        serialized_map = {k: v.to_dict() for k, v in current_map.items()}

        uow_id = f"suspend::{effect.effect_id}"
        uow = make_uow(
            identity=uow_id,
            routes=[
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(Mutation(MutationOp.SET, ORCH_EFFECTS_KEY, serialized_map),),
                    successor=Successor.halt(),
                )
            ],
            matrix_cell=EFFECT_CELL,
            parent_context="effects",
        )
        prop = propose(uow, curr_state)
        tx = create_transaction_descriptor(uow, curr_state, write_set=(ORCH_EFFECTS_KEY,))
        cert = certify(uow, curr_state, prop)
        self.sequencer.commit(uow, prop, tx, cert)
        return eff_pending

    def commit_receipt(self, effect: EffectDescriptor, receipt: EffectReceipt) -> EffectDescriptor:
        """Certifies receipt and commits final result into authoritative state."""
        verify_effect_receipt_binding(effect, receipt, expected_signer=self.expected_signer)
        curr_state = self.sequencer.current_state

        eff_result = replace(
            effect,
            status=EffectStatus.COMMITTED_RESULT,
            observation=receipt.response_payload,
            receipt=receipt,
        )

        current_map = get_effects_map(curr_state)
        current_map[eff_result.effect_id] = eff_result
        serialized_map = {k: v.to_dict() for k, v in current_map.items()}

        uow_id = f"result::{effect.effect_id}"
        uow = make_uow(
            identity=uow_id,
            routes=[
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(Mutation(MutationOp.SET, ORCH_EFFECTS_KEY, serialized_map),),
                    successor=Successor.halt(),
                )
            ],
            matrix_cell=EFFECT_CELL,
            parent_context="effects",
        )
        prop = propose(uow, curr_state)
        tx = create_transaction_descriptor(uow, curr_state, write_set=(ORCH_EFFECTS_KEY,))
        cert = certify(uow, curr_state, prop)
        self.sequencer.commit(uow, prop, tx, cert)
        return eff_result
