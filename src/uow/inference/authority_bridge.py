"""Protocol Authority Bridge: Maps Unprivileged Neural Proposals to Deterministic UoW Certification.

Enforces the core protocol invariant:
The Inference Gateway produces unprivileged, advisory typed proposals.
Only the deterministic UoW certification kernel and EvidenceLedger have authority
to validate pre-states, verify transition guards, and commit state transitions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from src.uow.contracts import UoW, Route, SuccessorKind
from src.uow.state import WorldState
from src.uow.engine import Proposal, CertificateResult, EvidenceRecord, certify, EvidenceLedger
from src.uow.inference.request_context import InferenceResponse, TypedProposal


@dataclass(frozen=True)
class AuthorityEvaluation:
    """Outcome of submitting an unprivileged inference proposal to the UoW Authority Kernel."""
    is_schema_valid: bool
    is_authority_certified: bool
    rejection_reason: Optional[str]
    certificate_hash: str
    pre_state_hash: str
    post_state_hash: str
    evidence_record: Optional[EvidenceRecord] = None


class AuthorityBridge:
    """Deterministic bridge linking the probabilistic inference gateway to UoW authority."""

    @staticmethod
    def evaluate_and_commit(
        response: InferenceResponse,
        uow: UoW,
        pre_state: WorldState,
        ledger: EvidenceLedger,
    ) -> AuthorityEvaluation:
        """Evaluates an inference response against UoW contract and pre-state.
        
        If valid: commits evidence record to the ledger.
        If invalid: rejects with explicit diagnostic reason. Zero unauthorized commits.
        """
        # 1. Check L0: Schema validity from inference response
        if response.status != "OK" or not isinstance(response.result, TypedProposal):
            return AuthorityEvaluation(
                is_schema_valid=False,
                is_authority_certified=False,
                rejection_reason=f"INFERENCE_STATUS_NOT_OK:{response.error_message or response.status}",
                certificate_hash="",
                pre_state_hash=pre_state.state_hash,
                post_state_hash=pre_state.state_hash,
            )

        payload = response.result.payload
        if not isinstance(payload, dict):
            return AuthorityEvaluation(
                is_schema_valid=False,
                is_authority_certified=False,
                rejection_reason="PAYLOAD_NOT_DICT",
                certificate_hash="",
                pre_state_hash=pre_state.state_hash,
                post_state_hash=pre_state.state_hash,
            )

        # Check for unresolved references / missing attributes
        unknowns = payload.get("unknowns", [])
        if unknowns:
            return AuthorityEvaluation(
                is_schema_valid=True,
                is_authority_certified=False,
                rejection_reason=f"UNRESOLVED_REFERENCES:{unknowns}",
                certificate_hash="",
                pre_state_hash=pre_state.state_hash,
                post_state_hash=pre_state.state_hash,
            )

        # 2. Match proposed action to a deterministic route in the target UoW
        action = payload.get("action")
        target_route_idx: Optional[int] = None
        for idx, route in enumerate(uow.Gamma.routes):
            # If route matches action name in metadata or tags
            route_meta = getattr(route, "metadata", {}) or {}
            route_action = route_meta.get("action") or (route.successor.value if route.successor else None)
            if route_action == action or str(action).lower() in str(route).lower():
                target_route_idx = idx
                break

        if target_route_idx is None:
            # Fallback to route 0 if uow has only 1 route
            if len(uow.Gamma.routes) == 1:
                target_route_idx = 0
            else:
                return AuthorityEvaluation(
                    is_schema_valid=True,
                    is_authority_certified=False,
                    rejection_reason=f"NO_MATCHING_ROUTE_FOR_ACTION:{action}",
                    certificate_hash="",
                    pre_state_hash=pre_state.state_hash,
                    post_state_hash=pre_state.state_hash,
                )

        route = uow.Gamma.routes[target_route_idx]

        # 3. Construct candidate proposed state via route mutations
        try:
            mutated = route.apply_mutations(pre_state)
            successor = route.successor.resolve(mutated)
            halted = route.successor.kind is SuccessorKind.HALT

            if halted:
                status = mutated.status if mutated.status != "RUNNING" else "HALTED"
                proposed_state = mutated.with_status(status).with_cursor(None)
            elif route.successor.kind is SuccessorKind.PRESERVE:
                proposed_state = mutated.with_status(pre_state.status).with_cursor(pre_state.cursor)
            else:
                proposed_state = mutated.with_cursor(successor)

            candidate_proposal = Proposal(
                uow_id=uow.H.identity,
                pre_state_hash=pre_state.state_hash,
                selected_route_index=target_route_idx,
                proposed_state=proposed_state,
                selected_successor=successor,
                halted=halted,
            )
        except Exception as e:
            return AuthorityEvaluation(
                is_schema_valid=True,
                is_authority_certified=False,
                rejection_reason=f"PROPOSAL_CONSTRUCTION_ERROR:{e}",
                certificate_hash="",
                pre_state_hash=pre_state.state_hash,
                post_state_hash=pre_state.state_hash,
            )

        # 4. Certify candidate proposal with UoW certification kernel
        cert = certify(uow, pre_state, candidate_proposal)
        if not cert.is_valid:
            return AuthorityEvaluation(
                is_schema_valid=True,
                is_authority_certified=False,
                rejection_reason=cert.rejection_reason,
                certificate_hash="",
                pre_state_hash=pre_state.state_hash,
                post_state_hash=pre_state.state_hash,
            )

        # 5. Commit certified transition to EvidenceLedger
        step_number = len(ledger.records) + 1
        rec = EvidenceRecord(
            step_number=step_number,
            uow_id=uow.H.identity,
            source_category=uow.H.source_category,
            target_category=uow.H.target_category,
            pre_state_hash=pre_state.state_hash,
            selected_route_index=target_route_idx,
            proposed_state_hash=proposed_state.state_hash,
            certificate_hash=cert.certificate_hash,
            post_state_hash=proposed_state.state_hash,
            next_uow_pointer=successor,
            prev_evidence_hash=ledger.root_hash(),
        )
        ledger.append(rec)

        return AuthorityEvaluation(
            is_schema_valid=True,
            is_authority_certified=True,
            rejection_reason=None,
            certificate_hash=cert.certificate_hash,
            pre_state_hash=pre_state.state_hash,
            post_state_hash=proposed_state.state_hash,
            evidence_record=rec,
        )
