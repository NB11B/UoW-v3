from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[4]


def _oracle_text():
    return (REPO / "experiments" / "reference-oracles" / "oracles.yaml").read_text(encoding="utf-8")


def _gate_text():
    return (REPO / "experiments" / "reference-oracles" / "gate_map.yaml").read_text(encoding="utf-8")


def test_r7_all_thirteen_policy_invariants_have_target_gate_mappings():
    oracle = _oracle_text()
    block = oracle.split("POLICY_ORCHESTRATOR_P1_P5:", 1)[1].split("A4_ONTOLOGY_ADAPTATION:", 1)[0]
    invariant_block = block.split("invariants:", 1)[1]
    invariants = re.findall(r"^      - ([a-z0-9_]+)$", invariant_block, flags=re.MULTILINE)

    gate = _gate_text()
    policy_block = gate.split("policy_p1_p5:", 1)[1].split("\na3:", 1)[0]

    assert len(invariants) == 13
    for invariant in invariants:
        assert re.search(rf"^    {re.escape(invariant)}:$", policy_block, flags=re.MULTILINE), invariant


def test_r7_a4_mapping_is_explicitly_conceptual_not_qualified():
    gate = _gate_text()
    a4 = gate.split("\na4:", 1)[1]

    assert "status: CONCEPTUAL_UNQUALIFIED" in a4
    assert "target: [specification/ontology]" in a4
    assert "ontology_transition_authority" in a4


def test_r7_policy_and_ontology_surfaces_exist():
    assert (REPO / "specification" / "policy" / "README.md").exists()
    assert (REPO / "specification" / "ontology" / "README.md").exists()
