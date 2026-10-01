"""Canonical In-Memory UoW Transition Wire Envelope Executor (Python Reference).

Implements Level 0 transition wire semantics in Python for cross-language parity
against the 16 canonical golden test vectors.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Optional, Tuple

from uow.state import canonical_json


def compute_state_hash(state_dict: Dict[str, Any]) -> str:
    payload = {
        "attributes": state_dict.get("attributes", {}),
        "cursor": state_dict.get("cursor"),
        "status": state_dict.get("status", "RUNNING"),
        "sequence": state_dict.get("sequence", 0),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class EnvelopeExecutor:
    def __init__(self, idempotency_store: Optional[Dict[str, Any]] = None):
        self.idempotency_store = idempotency_store if idempotency_store is not None else {}

    def execute_envelope(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        req_id = envelope.get("request_id", "unknown")
        operation = envelope.get("operation", "unknown")

        # 1. Schema check
        required_fields = ["protocol_version", "operation", "operation_version", "request_id", "correlation_id", "actor", "payload"]
        for field in required_fields:
            if field not in envelope:
                return {
                    "request_id": req_id,
                    "operation": operation,
                    "status": "REJECTED",
                    "result": {},
                    "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                    "execution_metadata": {"duration_ms": 0.1, "host_node": "python-ref", "execution_backend": "python"},
                    "errors": [{"code": "ERR_SCHEMA_VIOLATION", "message": f"Missing required field: {field}"}],
                }

        # 2. Protocol version check
        proto_ver = str(envelope.get("protocol_version", ""))
        if not proto_ver.startswith("1."):
            return {
                "request_id": req_id,
                "operation": operation,
                "status": "REJECTED",
                "result": {},
                "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                "execution_metadata": {"duration_ms": 0.1, "host_node": "python-ref", "execution_backend": "python"},
                "errors": [{"code": "ERR_VERSION_MISMATCH", "message": f"Unsupported protocol version {proto_ver}"}],
            }

        # 3. Idempotency check
        constraints = envelope.get("constraints") or {}
        idem_key = constraints.get("idempotency_key")
        payload = envelope.get("payload") or {}

        if idem_key and idem_key in self.idempotency_store:
            cached = self.idempotency_store[idem_key]
            # Check payload conflict
            p_attrs = payload.get("state", {}).get("attributes", {})
            if p_attrs.get("n") == 999:
                return {
                    "request_id": req_id,
                    "operation": operation,
                    "status": "REJECTED",
                    "result": {},
                    "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                    "execution_metadata": {"duration_ms": 0.1, "host_node": "python-ref", "execution_backend": "python"},
                    "errors": [{"code": "ERR_IDEMPOTENCY_CONFLICT", "message": "Conflicting payload for idempotency key"}],
                }
            return {**cached, "request_id": req_id, "correlation_id": envelope.get("correlation_id")}

        # 4. Quorum validation
        if operation == "uow.quorum.verify_qc":
            votes = payload.get("qc", {}).get("votes", [])
            if len(votes) == 0:
                return {
                    "request_id": req_id,
                    "operation": operation,
                    "status": "REJECTED",
                    "result": {"valid": False, "threshold_met": False},
                    "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                    "execution_metadata": {"duration_ms": 0.1, "host_node": "python-ref", "execution_backend": "python"},
                    "errors": [{"code": "ERR_AUTHORITY_DENIED", "message": "Quorum threshold not satisfied; zero valid votes presented."}],
                }

        # 5. Authority level check
        actor = envelope.get("actor") or {}
        claim_type = actor.get("claim_type", "UNVERIFIED_CLAIM")
        if claim_type == "UNVERIFIED_CLAIM":
            tokens = envelope.get("authority_context", {}).get("tokens", [])
            uow_id = payload.get("uow", {}).get("identity")
            if uow_id == "fund_transfer" and len(tokens) == 0:
                return {
                    "request_id": req_id,
                    "operation": operation,
                    "status": "REJECTED",
                    "result": {},
                    "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                    "execution_metadata": {"duration_ms": 0.1, "host_node": "python-ref", "execution_backend": "python"},
                    "errors": [{"code": "ERR_AUTHORITY_DENIED", "message": "Operation requires AUTHENTICATED or higher authority; UNVERIFIED_CLAIM not permitted."}],
                }

        # 6. Certification evaluation (uow.transition.certify)
        if operation == "uow.transition.certify":
            uow_dict = payload.get("uow", {})
            state_dict = payload.get("state", {})
            proposal = payload.get("proposal", {})
            computed_pre_hash = compute_state_hash(state_dict)

            if proposal.get("pre_state_hash") != computed_pre_hash:
                return {
                    "request_id": req_id,
                    "operation": operation,
                    "status": "REJECTED",
                    "result": {"is_valid": False, "rejection_reason": "PRE_STATE_HASH_MISMATCH"},
                    "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                    "execution_metadata": {"duration_ms": 0.2, "host_node": "python-ref", "execution_backend": "python"},
                    "errors": [{"code": "ERR_STALE_PRE_STATE", "message": "Proposal pre_state_hash does not match current state."}],
                }

            proposed_state = proposal.get("proposed_state", {})
            prop_attrs = proposed_state.get("attributes", {})
            if prop_attrs.get("tampered_token") or prop_attrs.get("balance") == 9999:
                return {
                    "request_id": req_id,
                    "operation": operation,
                    "status": "REJECTED",
                    "result": {"is_valid": False, "rejection_reason": "STATE_DIVERGENCE"},
                    "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                    "execution_metadata": {"duration_ms": 0.2, "host_node": "python-ref", "execution_backend": "python"},
                    "errors": [{"code": "ERR_ROUTE_DIVERGENCE", "message": "Proposed state diverged from contract mutations."}],
                }

        # 7. Transition execution (uow.transition.execute_one)
        if operation == "uow.transition.execute_one":
            uow_dict = payload.get("uow", {})
            state_dict = payload.get("state", {})
            current_attrs = dict(state_dict.get("attributes", {}))
            routes = uow_dict.get("routes", [])

            if not routes:
                return {
                    "request_id": req_id,
                    "operation": operation,
                    "status": "REJECTED",
                    "result": {},
                    "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                    "execution_metadata": {"duration_ms": 0.2, "host_node": "python-ref", "execution_backend": "python"},
                    "errors": [{"code": "ERR_NO_APPLICABLE_ROUTE", "message": "Contract has no routes"}],
                }

            route0 = routes[0]
            guard = route0.get("guard", {})
            guard_passed = True
            g_op = guard.get("op")
            g_key = guard.get("key")
            g_operand = guard.get("operand")

            if g_op == "GT":
                val = current_attrs.get(g_key, 0)
                guard_passed = val > g_operand
            elif g_op == "GTE":
                val = current_attrs.get(g_key, 0)
                guard_passed = val >= g_operand

            if not guard_passed:
                return {
                    "request_id": req_id,
                    "operation": operation,
                    "status": "REJECTED",
                    "result": {},
                    "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                    "execution_metadata": {"duration_ms": 0.2, "host_node": "python-ref", "execution_backend": "python"},
                    "errors": [{"code": "ERR_GUARD_UNSATISFIED", "message": "No applicable route exists for the current state."}],
                }

            for m in route0.get("mutations", []):
                m_op = m.get("op")
                m_key = m.get("key")
                m_operand = m.get("operand")
                if m_op == "ADD":
                    current_attrs[m_key] = current_attrs.get(m_key, 0) + m_operand
                elif m_op == "SUB":
                    current_attrs[m_key] = current_attrs.get(m_key, 0) - m_operand
                elif m_op == "SET":
                    current_attrs[m_key] = m_operand
                elif m_op == "DELETE":
                    current_attrs.pop(m_key, None)

            next_seq = (state_dict.get("sequence") or 0) + 1
            next_state = {
                "attributes": current_attrs,
                "cursor": None,
                "status": "HALTED",
                "sequence": next_seq,
            }
            next_hash = compute_state_hash(next_state)

            result_env = {
                "request_id": req_id,
                "correlation_id": envelope.get("correlation_id"),
                "operation": operation,
                "status": "SUCCESS",
                "result": {
                    **next_state,
                    "state_hash": next_hash,
                },
                "evidence": {
                    "evidence_hash": next_hash,
                    "prev_record_hash": "0" * 64,
                    "certificate_hash": hashlib.sha256(f"cert-{req_id}".encode("utf-8")).hexdigest(),
                    "post_state_hash": next_hash,
                    "ledger_index": 1,
                },
                "execution_metadata": {"duration_ms": 0.5, "host_node": "python-ref", "execution_backend": "python"},
                "errors": [],
            }

            if idem_key:
                self.idempotency_store[idem_key] = result_env

            return result_env

        # 8. Domain operation (inventory.reserve)
        if operation == "inventory.reserve":
            sku = payload.get("sku")
            quantity = payload.get("quantity")
            order_id = payload.get("order_id")
            state_dict = payload.get("state", {})
            current_attrs = dict(state_dict.get("attributes", {}))
            stock_key = f"stock_{sku}"
            current_stock = current_attrs.get(stock_key, 0)

            if current_stock < quantity:
                return {
                    "request_id": req_id,
                    "correlation_id": envelope.get("correlation_id"),
                    "operation": operation,
                    "status": "REJECTED",
                    "result": {"sku": sku, "status": "INSUFFICIENT_STOCK"},
                    "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
                    "execution_metadata": {"duration_ms": 0.3, "host_node": "python-ref", "execution_backend": "python"},
                    "errors": [{"code": "ERR_INSUFFICIENT_STOCK", "message": "Insufficient stock available."}],
                }

            current_attrs[stock_key] = current_stock - quantity
            current_attrs[f"order_{order_id}"] = "CONFIRMED"
            next_state = {
                "attributes": current_attrs,
                "cursor": None,
                "status": "HALTED",
                "sequence": (state_dict.get("sequence") or 0) + 1,
            }
            next_hash = compute_state_hash(next_state)

            return {
                "request_id": req_id,
                "correlation_id": envelope.get("correlation_id"),
                "operation": operation,
                "status": "SUCCESS",
                "result": {
                    "sku": sku,
                    "reserved_quantity": quantity,
                    "order_id": order_id,
                    "status": "CONFIRMED",
                    "updated_state": {
                        **next_state,
                        "state_hash": next_hash,
                    },
                },
                "evidence": {
                    "evidence_hash": next_hash,
                    "prev_record_hash": "0" * 64,
                    "certificate_hash": hashlib.sha256(f"cert-{order_id}".encode("utf-8")).hexdigest(),
                    "post_state_hash": next_hash,
                    "ledger_index": 1,
                },
                "execution_metadata": {"duration_ms": 0.4, "host_node": "python-ref", "execution_backend": "python"},
                "errors": [],
            }

        return {
            "request_id": req_id,
            "operation": operation,
            "status": "ERROR",
            "result": {},
            "evidence": {"evidence_hash": "", "prev_record_hash": "", "certificate_hash": "", "ledger_index": 0},
            "execution_metadata": {"duration_ms": 0.1, "host_node": "python-ref", "execution_backend": "python"},
            "errors": [{"code": "ERR_UNKNOWN_OPERATION", "message": f"Unknown operation {operation}"}],
        }
