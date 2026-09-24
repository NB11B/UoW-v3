from pathlib import Path
import re


def _text():
    repo = Path(__file__).resolve().parents[4]
    return (repo / "experiments" / "reference-oracles" / "oracles.yaml").read_text(encoding="utf-8")


def test_reference_oracle_manifest_preserves_evidence_classes():
    text = _text()
    assert "A2_PORTABLE_CAPSTONE:" in text
    assert "evidence_status: QUALIFIED_PORTABLE" in text
    assert "A3_ADAPTIVE_COMPUTE_EFFICIENCY:" in text
    assert "evidence_status: QUALIFIED_MIXED_PORTABLE_PHYSICAL" in text
    assert "POLICY_ORCHESTRATOR_P1_P5:" in text
    assert "evidence_status: QUALIFIED_FROZEN_REFERENCE" in text
    assert "A4_ONTOLOGY_ADAPTATION:" in text
    assert "evidence_status: CONCEPTUAL_UNQUALIFIED" in text


def test_policy_reference_has_exactly_thirteen_acceptance_invariants():
    text = _text()
    block = text.split("POLICY_ORCHESTRATOR_P1_P5:", 1)[1].split("A4_ONTOLOGY_ADAPTATION:", 1)[0]
    invariant_block = block.split("invariants:", 1)[1]
    invariants = re.findall(r"^      - ([a-z0-9_]+)$", invariant_block, flags=re.MULTILINE)
    assert len(invariants) == 13
    assert len(set(invariants)) == 13


def test_policy_reference_is_downstream_of_a3_without_double_counting():
    text = _text()
    block = text.split("POLICY_ORCHESTRATOR_P1_P5:", 1)[1].split("A4_ONTOLOGY_ADAPTATION:", 1)[0]
    assert "downstream_of: A3_ADAPTIVE_COMPUTE_EFFICIENCY" in block
    assert "evidence_double_counting_forbidden: true" in block
    assert "further_feature_milestone_required: false" in block


def test_a4_remains_conceptual_until_future_qualification():
    text = _text()
    block = text.split("A4_ONTOLOGY_ADAPTATION:", 1)[1]
    assert "evidence_status: CONCEPTUAL_UNQUALIFIED" in block
    assert "branch: null" in block
    assert "tag: null" in block
    assert "qualification_status: NOT_STARTED" in block
    assert "do_not_hardcode_python_ontology_as_universal_protocol" in block
