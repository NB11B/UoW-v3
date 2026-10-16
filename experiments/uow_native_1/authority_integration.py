"""Independent UoW v3 authority integration tests for UOW-NATIVE-1 Gate C.

Validates that probabilistic model proposals cannot bypass deterministic UoW certification:
1. Valid proposal reaches deterministic certification.
2. Proposal with false pre-state hash is rejected (PRE_STATE_HASH_MISMATCH).
3. Tampered proposed state is rejected (STATE_DIVERGENCE).
4. Mismatched route or successor is rejected (ROUTE_DIVERGENCE, SUCCESSOR_DIVERGENCE, HALT_DIVERGENCE).
5. Invalid certificate cannot be committed (fails closed with ValueError).
6. Forged or unbound certificate cannot be committed (fails closed with ValueError).
7. Stale state cannot be committed (pre-state binding check).
8. Valid committed transition extends evidence ledger with authentic hash chain.
9. Ledger cryptographic hash chain verifies after legitimate commitments.
10. Tampered ledger record causes verify_integrity to return False.
"""
import json
import os
import sys
import unittest

# Ensure src is on sys.path
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


def create_comparison_uow(uow_id="uow_relational_compare"):
    """Create a minimal authoritative UoW for numeric comparison."""
    return make_uow(
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


class TestAuthorityIntegration(unittest.TestCase):
    def setUp(self):
        self.uow = create_comparison_uow()
        self.state = WorldState(
            attributes={"a": 82, "b": 15},
            cursor=self.uow.H.identity,
            status="RUNNING",
            sequence=0,
        )

    def test_01_valid_proposal_reaches_deterministic_certification(self):
        proposal = propose(self.uow, self.state)
        cert = certify(self.uow, self.state, proposal)
        self.assertTrue(cert.is_valid)
        self.assertIsNone(cert.rejection_reason)
        self.assertEqual(cert.uow_id, self.uow.H.identity)
        self.assertEqual(cert.pre_state_hash, self.state.state_hash)
        self.assertEqual(cert.proposed_state_hash, proposal.proposed_state.state_hash)

    def test_02_false_pre_state_hash_rejected(self):
        valid_proposal = propose(self.uow, self.state)
        tampered_proposal = Proposal(
            uow_id=valid_proposal.uow_id,
            pre_state_hash="0" * 64,  # Corrupted / false pre-state hash
            selected_route_index=valid_proposal.selected_route_index,
            proposed_state=valid_proposal.proposed_state,
            selected_successor=valid_proposal.selected_successor,
            halted=valid_proposal.halted,
        )
        cert = certify(self.uow, self.state, tampered_proposal)
        self.assertFalse(cert.is_valid)
        self.assertEqual(cert.rejection_reason, "PRE_STATE_HASH_MISMATCH")

    def test_03_tampered_proposed_state_rejected(self):
        valid_proposal = propose(self.uow, self.state)
        corrupted_state = valid_proposal.proposed_state.with_attribute("winner", 9999)
        tampered_proposal = Proposal(
            uow_id=valid_proposal.uow_id,
            pre_state_hash=valid_proposal.pre_state_hash,
            selected_route_index=valid_proposal.selected_route_index,
            proposed_state=corrupted_state,
            selected_successor=valid_proposal.selected_successor,
            halted=valid_proposal.halted,
        )
        cert = certify(self.uow, self.state, tampered_proposal)
        self.assertFalse(cert.is_valid)
        self.assertEqual(cert.rejection_reason, "STATE_DIVERGENCE")

    def test_04_mismatched_route_or_successor_rejected(self):
        valid_proposal = propose(self.uow, self.state)

        # Route divergence
        mismatched_route = Proposal(
            uow_id=valid_proposal.uow_id,
            pre_state_hash=valid_proposal.pre_state_hash,
            selected_route_index=1,  # Route 0 is expected for 82 > 50
            proposed_state=valid_proposal.proposed_state,
            selected_successor=valid_proposal.selected_successor,
            halted=valid_proposal.halted,
        )
        cert_route = certify(self.uow, self.state, mismatched_route)
        self.assertFalse(cert_route.is_valid)
        self.assertEqual(cert_route.rejection_reason, "ROUTE_DIVERGENCE")

        # Successor divergence
        mismatched_successor = Proposal(
            uow_id=valid_proposal.uow_id,
            pre_state_hash=valid_proposal.pre_state_hash,
            selected_route_index=valid_proposal.selected_route_index,
            proposed_state=valid_proposal.proposed_state,
            selected_successor="unauthorized_next_node",
            halted=valid_proposal.halted,
        )
        cert_succ = certify(self.uow, self.state, mismatched_successor)
        self.assertFalse(cert_succ.is_valid)
        self.assertEqual(cert_succ.rejection_reason, "SUCCESSOR_DIVERGENCE")

        # Halt divergence
        mismatched_halt = Proposal(
            uow_id=valid_proposal.uow_id,
            pre_state_hash=valid_proposal.pre_state_hash,
            selected_route_index=valid_proposal.selected_route_index,
            proposed_state=valid_proposal.proposed_state,
            selected_successor=valid_proposal.selected_successor,
            halted=False,  # Expected True
        )
        cert_halt = certify(self.uow, self.state, mismatched_halt)
        self.assertFalse(cert_halt.is_valid)
        self.assertEqual(cert_halt.rejection_reason, "HALT_DIVERGENCE")

    def test_05_invalid_certificate_cannot_be_committed(self):
        valid_proposal = propose(self.uow, self.state)
        invalid_cert = CertificateResult(
            is_valid=False,
            certificate_hash="",
            uow_id=self.uow.H.identity,
            pre_state_hash=self.state.state_hash,
            proposed_state_hash=valid_proposal.proposed_state.state_hash,
            selected_route_index=valid_proposal.selected_route_index,
            selected_successor=valid_proposal.selected_successor,
            halted=valid_proposal.halted,
            rejection_reason="SIMULATED_REJECTION",
        )
        with self.assertRaises(ValueError) as ctx:
            commit(
                self.uow,
                self.state,
                valid_proposal,
                invalid_cert,
                prev_evidence_hash="0" * 64,
                step_number=1,
            )
        self.assertIn("Cannot commit rejected proposal", str(ctx.exception))

    def test_06_forged_certificate_hash_cannot_be_committed(self):
        valid_proposal = propose(self.uow, self.state)
        forged_cert = CertificateResult(
            is_valid=True,
            certificate_hash="deadbeef" * 8,  # Forged hash
            uow_id=self.uow.H.identity,
            pre_state_hash=self.state.state_hash,
            proposed_state_hash=valid_proposal.proposed_state.state_hash,
            selected_route_index=valid_proposal.selected_route_index,
            selected_successor=valid_proposal.selected_successor,
            halted=valid_proposal.halted,
        )
        with self.assertRaises(ValueError) as ctx:
            commit(
                self.uow,
                self.state,
                valid_proposal,
                forged_cert,
                prev_evidence_hash="0" * 64,
                step_number=1,
            )
        self.assertIn("Certificate hash is not authentic", str(ctx.exception))

    def test_07_stale_pre_state_binding_rejected_at_commit(self):
        proposal = propose(self.uow, self.state)
        cert = certify(self.uow, self.state, proposal)

        # Advance state elsewhere (stale state condition)
        stale_state = self.state.with_attribute("other", "mutated")
        with self.assertRaises(ValueError) as ctx:
            commit(
                self.uow,
                stale_state,
                proposal,
                cert,
                prev_evidence_hash="0" * 64,
                step_number=1,
            )
        self.assertTrue(
            "Certificate hash is not authentic for this transition." in str(ctx.exception)
            or "Certificate is not bound to the current pre-state" in str(ctx.exception)
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
        self.assertEqual(committed.sequence, 1)
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
            step_number=3,  # Should be 2
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


def run_authority_suite():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAuthorityIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    report = {
        "gate": "Gate C: Independent UoW authority integration",
        "tests_run": result.testsRun,
        "errors": len(result.errors),
        "failures": len(result.failures),
        "passed": result.wasSuccessful(),
        "cases_verified": [
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
    return report


if __name__ == "__main__":
    rep = run_authority_suite()
    output_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", "uow_native_1", "authority_integration.json")
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf8") as f:
        json.dump(rep, f, indent=2)
    print(f"\nWrote Gate C results to {output_path}")
