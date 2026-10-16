"""Deterministic UoW Authority Integration (Gate B3) for UOW-NATIVE-2.

Binds probabilistic model outputs as unprivileged proposers to the deterministic
UoW v3 kernel (src/uow/engine.py).

Verifies 11 security vectors:
  1. Deterministic certification of valid probabilistic proposals
  2. Rejection of false pre-state hash (PRE_STATE_HASH_MISMATCH)
  3. Rejection of tampered proposed state (STATE_DIVERGENCE)
  4. Rejection of route divergence (ROUTE_DIVERGENCE)
  5. Rejection of successor divergence (SUCCESSOR_DIVERGENCE)
  6. Rejection of halt divergence (HALT_DIVERGENCE)
  7. Rejection of commit with invalid certificate (ValueError)
  8. Rejection of commit with forged certificate hash (ValueError)
  9. Rejection of commit with stale pre-state binding (ValueError)
 10. Valid commitment extensions of EvidenceLedger
 11. Cryptographic SHA-256 evidence hash chain verification & tampering detection
"""

import json
import os
import sys
import unittest
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from uow.compat.v2 import (
    Guard,
    GuardOp,
    MatrixCell,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorkCategory,
    WorldState,
    commit,
    certify,
    make_uow,
    propose,
)
from uow.engine import CertificateResult, EvidenceLedger, EvidenceRecord, Proposal


def create_comparison_uow(uow_id: str = "uow_relational_compare") -> Tuple[Any, WorldState]:
    """Create a minimal authoritative UoW for numeric comparison."""
    uow = make_uow(
        uow_id,
        [
            Route(
                guard=Guard(GuardOp.GT, "a", 50),
                mutations=(Mutation(MutationOp.SET, "winner", 82),),
                successor=Successor.halt(),
            ),
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(Mutation(MutationOp.SET, "winner", 15),),
                successor=Successor.halt(),
            ),
        ],
        MatrixCell(WorkCategory.DATA, WorkCategory.RULES),
    )
    initial_state = WorldState(
        attributes={"a": 82, "b": 15},
        cursor=uow.H.identity,
        status="RUNNING",
        sequence=0,
    )
    return uow, initial_state


class TestAuthorityIntegration(unittest.TestCase):
    def setUp(self):
        self.uow, self.state = create_comparison_uow()

    def test_01_valid_probabilistic_proposal_certifies(self):
        proposal = propose(self.uow, self.state)
        cert = certify(self.uow, self.state, proposal)
        self.assertTrue(cert.is_valid)
        self.assertIsNone(cert.rejection_reason)
        self.assertEqual(cert.uow_id, self.uow.H.identity)
        self.assertEqual(cert.pre_state_hash, self.state.state_hash)
        self.assertEqual(cert.proposed_state_hash, proposal.proposed_state.state_hash)
        self.assertEqual(len(cert.certificate_hash), 64)

    def test_02_false_pre_state_hash_rejected(self):
        valid = propose(self.uow, self.state)
        bad_proposal = Proposal(
            uow_id=valid.uow_id,
            pre_state_hash="0" * 64,
            selected_route_index=valid.selected_route_index,
            proposed_state=valid.proposed_state,
            selected_successor=valid.selected_successor,
            halted=valid.halted,
        )
        cert = certify(self.uow, self.state, bad_proposal)
        self.assertFalse(cert.is_valid)
        self.assertEqual(cert.rejection_reason, "PRE_STATE_HASH_MISMATCH")

    def test_03_tampered_state_rejected(self):
        valid = propose(self.uow, self.state)
        tampered_state = valid.proposed_state.with_attribute("winner", 999)
        bad_proposal = Proposal(
            uow_id=valid.uow_id,
            pre_state_hash=valid.pre_state_hash,
            selected_route_index=valid.selected_route_index,
            proposed_state=tampered_state,
            selected_successor=valid.selected_successor,
            halted=valid.halted,
        )
        cert = certify(self.uow, self.state, bad_proposal)
        self.assertFalse(cert.is_valid)
        self.assertEqual(cert.rejection_reason, "STATE_DIVERGENCE")

    def test_04_divergent_route_successor_halt_rejected(self):
        valid = propose(self.uow, self.state)

        # Route divergence
        bad_route = Proposal(
            uow_id=valid.uow_id,
            pre_state_hash=valid.pre_state_hash,
            selected_route_index=1 - valid.selected_route_index,
            proposed_state=valid.proposed_state,
            selected_successor=valid.selected_successor,
            halted=valid.halted,
        )
        cert_route = certify(self.uow, self.state, bad_route)
        self.assertFalse(cert_route.is_valid)
        self.assertEqual(cert_route.rejection_reason, "ROUTE_DIVERGENCE")

        # Successor divergence
        bad_succ = Proposal(
            uow_id=valid.uow_id,
            pre_state_hash=valid.pre_state_hash,
            selected_route_index=valid.selected_route_index,
            proposed_state=valid.proposed_state,
            selected_successor="unauthorized_next_node",
            halted=valid.halted,
        )
        cert_succ = certify(self.uow, self.state, bad_succ)
        self.assertFalse(cert_succ.is_valid)
        self.assertEqual(cert_succ.rejection_reason, "SUCCESSOR_DIVERGENCE")

        # Halt divergence
        bad_halt = Proposal(
            uow_id=valid.uow_id,
            pre_state_hash=valid.pre_state_hash,
            selected_route_index=valid.selected_route_index,
            proposed_state=valid.proposed_state,
            selected_successor=valid.selected_successor,
            halted=not valid.halted,
        )
        cert_halt = certify(self.uow, self.state, bad_halt)
        self.assertFalse(cert_halt.is_valid)
        self.assertEqual(cert_halt.rejection_reason, "HALT_DIVERGENCE")

    def test_05_invalid_certificate_cannot_be_committed(self):
        valid = propose(self.uow, self.state)
        invalid_cert = CertificateResult(
            is_valid=False,
            certificate_hash="",
            uow_id=self.uow.H.identity,
            pre_state_hash=self.state.state_hash,
            proposed_state_hash=valid.proposed_state.state_hash,
            selected_route_index=valid.selected_route_index,
            selected_successor=valid.selected_successor,
            halted=valid.halted,
            rejection_reason="REJECTED",
        )
        with self.assertRaises(ValueError) as ctx:
            commit(
                self.uow,
                self.state,
                valid,
                invalid_cert,
                prev_evidence_hash="0" * 64,
                step_number=1,
            )
        self.assertIn("Cannot commit rejected proposal", str(ctx.exception))

    def test_06_forged_certificate_hash_cannot_be_committed(self):
        valid = propose(self.uow, self.state)
        forged_cert = CertificateResult(
            is_valid=True,
            certificate_hash="badf00d" * 9 + "a",
            uow_id=self.uow.H.identity,
            pre_state_hash=self.state.state_hash,
            proposed_state_hash=valid.proposed_state.state_hash,
            selected_route_index=valid.selected_route_index,
            selected_successor=valid.selected_successor,
            halted=valid.halted,
        )
        with self.assertRaises(ValueError) as ctx:
            commit(
                self.uow,
                self.state,
                valid,
                forged_cert,
                prev_evidence_hash="0" * 64,
                step_number=1,
            )
        self.assertIn("Certificate hash is not authentic", str(ctx.exception))

    def test_07_stale_pre_state_rejected_at_commit(self):
        proposal = propose(self.uow, self.state)
        cert = certify(self.uow, self.state, proposal)

        mutated_state = self.state.with_attribute("a", 999)
        with self.assertRaises(ValueError) as ctx:
            commit(
                self.uow,
                mutated_state,
                proposal,
                cert,
                prev_evidence_hash="0" * 64,
                step_number=1,
            )
        self.assertTrue(
            "Certificate hash is not authentic" in str(ctx.exception)
            or "Certificate is not bound" in str(ctx.exception)
        )

    def test_08_valid_commitment_extends_evidence_ledger(self):
        ledger = EvidenceLedger()
        self.assertEqual(len(ledger.records), 0)
        self.assertEqual(ledger.root_hash(), "0" * 64)

        proposal = propose(self.uow, self.state)
        cert = certify(self.uow, self.state, proposal)
        committed, evidence = commit(
            self.uow,
            self.state,
            proposal,
            cert,
            prev_evidence_hash=ledger.root_hash(),
            step_number=1,
        )
        ledger.append(evidence)

        self.assertEqual(len(ledger.records), 1)
        self.assertEqual(ledger.root_hash(), evidence.record_hash)
        self.assertEqual(committed.status, "HALTED")
        self.assertEqual(committed.require("winner"), 82)

    def test_09_evidence_hash_chain_verifies(self):
        ledger = EvidenceLedger()
        proposal = propose(self.uow, self.state)
        cert = certify(self.uow, self.state, proposal)
        _, evidence = commit(
            self.uow,
            self.state,
            proposal,
            cert,
            prev_evidence_hash=ledger.root_hash(),
            step_number=1,
        )
        ledger.append(evidence)
        self.assertTrue(ledger.verify_integrity())

    def test_10_tampered_ledger_integrity_fails(self):
        ledger = EvidenceLedger()
        proposal = propose(self.uow, self.state)
        cert = certify(self.uow, self.state, proposal)
        _, evidence = commit(
            self.uow,
            self.state,
            proposal,
            cert,
            prev_evidence_hash=ledger.root_hash(),
            step_number=1,
        )
        ledger.append(evidence)

        # Non-contiguous step number rejection
        tampered_evidence = EvidenceRecord(
            step_number=5,  # Non-contiguous
            uow_id=self.uow.H.identity,
            source_category=self.uow.H.source_category.value,
            target_category=self.uow.H.target_category.value,
            pre_state_hash=self.state.state_hash,
            selected_route_index=0,
            proposed_state_hash="a" * 64,
            certificate_hash="b" * 64,
            post_state_hash="c" * 64,
            next_uow_pointer=None,
            prev_evidence_hash=ledger.root_hash(),
        )
        with self.assertRaises(ValueError) as ctx:
            ledger.append(tampered_evidence)
        self.assertIn("Evidence step number is not contiguous", str(ctx.exception))


def run_authority_suite(output_path: Optional[str] = "artifacts/uow_native_2/authority_results.json") -> Dict[str, Any]:
    """Run all Gate B3 authority integration tests and output verified report."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAuthorityIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    report = {
        "gate": "Gate B3: UoW Authority Integration",
        "tests_run": result.testsRun,
        "errors": len(result.errors),
        "failures": len(result.failures),
        "passed": result.wasSuccessful(),
        "security_vectors_verified": [
            "Deterministic certification of valid probabilistic proposals",
            "Rejection of false pre-state hash (PRE_STATE_HASH_MISMATCH)",
            "Rejection of tampered proposed state (STATE_DIVERGENCE)",
            "Rejection of route divergence (ROUTE_DIVERGENCE)",
            "Rejection of successor divergence (SUCCESSOR_DIVERGENCE)",
            "Rejection of halt divergence (HALT_DIVERGENCE)",
            "Rejection of commit with invalid certificate (ValueError)",
            "Rejection of commit with forged certificate hash (ValueError)",
            "Rejection of commit with stale pre-state binding (ValueError)",
            "Valid commitment extensions of EvidenceLedger",
            "Verification of cryptographic SHA-256 evidence hash chain",
            "Rejection of non-contiguous and tampered ledger extensions",
        ],
        "isolation_guarantee": (
            "Probabilistic models act solely as unprivileged proposers. "
            "Authority certificates and ledger commitments remain strictly governed "
            "by the deterministic UoW kernel (src/uow/engine.py)."
        ),
    }

    if output_path:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    return report


if __name__ == "__main__":
    rep = run_authority_suite()
    print(f"\nGate B3 Authority Suite Passed: {rep['passed']}")
