"""Regression tests for UOW-NATIVE-3 Gate C3 deterministic authority verification."""
import unittest
from pathlib import Path
import sys

# Ensure src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from uow.compat.v2 import (
    DeterministicSequencer,
    EvidenceLedger,
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Proposal,
    Route,
    Successor,
    WorldState,
    certify,
    commit,
    make_uow,
)
from uow.semantic import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    IngressContext,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticDisposition,
    SemanticFrontierBuilder,
    SemanticHarness,
    SemanticRequirement,
    SemanticTranslationRequest,
)
from uow.semantic.adapters.codec import SemanticOutputParser, SemanticOutputValidationError
from uow.semantic.closure import SemanticClosureEngine
from uow.semantic.validation import DefaultSemanticAdmissibilityValidator


class TestC3Authority(unittest.TestCase):
    def setUp(self):
        self.parser = SemanticOutputParser()
        self.closure = SemanticClosureEngine(SemanticFrontierBuilder())
        self.req = SemanticTranslationRequest(
            signal=ExternalSignal(raw="Dispatch items immediately"),
            frontier=(SemanticRequirement("item"), SemanticRequirement("destination")),
            minimal_context=MinimalSemanticContext(state_hash="0"*64, state_sequence=0)
        )

    def test_malformed_syntax_fail_closed(self):
        malformed = "Some text with broken json {bindings: invalid"
        cand = self.parser.parse(malformed, self.req, evidence_ref="test", fail_closed=True)
        outcome = self.closure.close(
            signal=self.req.signal,
            requirements=self.req.frontier,
            context=self.req.minimal_context,
            initial_frontier=SemanticFrontierBuilder().build(self.req.frontier, self.req.minimal_context),
            translation=cand,
        )
        self.assertEqual(outcome.certificate.disposition, SemanticDisposition.CLARIFY)

    def test_unauthorized_terminal_rejected_and_fail_closed(self):
        injected = '{"bindings": [{"terminal": "root_privileges", "value": "grant"}], "alternatives": [], "unknowns": []}'
        with self.assertRaises(SemanticOutputValidationError):
            self.parser.parse(injected, self.req, evidence_ref="test", fail_closed=False)
        cand = self.parser.parse(injected, self.req, evidence_ref="test", fail_closed=True)
        self.assertEqual(len(cand.candidate_bindings), 0)
        self.assertEqual(set(cand.unknowns), {"item", "destination"})

    def test_context_overwrite_caught(self):
        req = SemanticTranslationRequest(
            signal=ExternalSignal(raw="Convey to Bay 3"),
            frontier=(SemanticRequirement("item"), SemanticRequirement("destination")),
            minimal_context=MinimalSemanticContext(
                state_hash="0"*64,
                state_sequence=0,
                bindings=(SemanticBinding("destination", "Bay_2", BindingOrigin.DETERMINISTIC),)
            )
        )
        output = '{"bindings": [{"terminal": "destination", "value": "Bay_3"}, {"terminal": "item", "value": "cells"}], "alternatives": [], "unknowns": []}'
        cand = self.parser.parse(output, req, evidence_ref="test", fail_closed=True)
        c_min_names = {b.terminal for b in req.minimal_context.bindings}
        has_overwrite = any(b.terminal in c_min_names for b in cand.candidate_bindings)
        self.assertTrue(has_overwrite)

    def test_admissibility_validator_rejects_ungrounded_entity(self):
        state = WorldState({"entities": {"item": ["cells", "sensors"]}})
        class Stub:
            def propose(self, r):
                return CandidateSemanticBindings(
                    candidate_bindings=(SemanticBinding("item", "quibble", BindingOrigin.PROBABILISTIC),)
                )
        harness = SemanticHarness(translator=Stub(), admissibility_validator=DefaultSemanticAdmissibilityValidator())
        res = harness.interpret(
            "Dispatch five quibble modules here immediately.",
            state=state,
            ingress=IngressContext(principal_id="u1", session_id="s1", channel="text"),
            requirements=(SemanticRequirement("item"),)
        )
        self.assertEqual(res.disposition, SemanticDisposition.CLARIFY)

    def test_kernel_refuses_uncertified_commits(self):
        base_state = WorldState(attributes={"balance": 100})
        task = make_uow(
            "transfer_uow",
            [
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(Mutation(MutationOp.SET, "balance", 50),),
                    successor=Successor.halt()
                )
            ]
        )
        invalid_proposal = Proposal(
            uow_id="transfer_uow",
            pre_state_hash="forged_pre_state_hash",
            selected_route_index=0,
            proposed_state=WorldState(attributes={"balance": 50}),
            selected_successor=None,
            halted=True
        )
        cert = certify(task, base_state, invalid_proposal)
        self.assertFalse(cert.is_valid)
        ledger = EvidenceLedger()
        with self.assertRaises(ValueError):
            commit(task, base_state, invalid_proposal, cert, prev_evidence_hash=ledger.root_hash(), step_number=1)
        self.assertEqual(len(ledger.records), 0)


if __name__ == "__main__":
    unittest.main()
