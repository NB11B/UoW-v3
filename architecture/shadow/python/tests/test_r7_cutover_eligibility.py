from pathlib import Path


REPO = Path(__file__).resolve().parents[4]


def test_r7_cutover_audit_requires_all_prior_stages():
    text = (REPO / "architecture" / "cutover_eligibility.yaml").read_text(encoding="utf-8")

    required = [
        "R0_frozen_control: PASS",
        "R1_architecture_evidence_mapping: PASS",
        "R2_language_neutral_specification: PASS",
        "R3_shadow_minimal_implementation: PASS_INITIAL",
        "R4_portable_experiment_reconstruction: PASS_INITIAL",
        "R5_cross_language_conformance: PASS_INITIAL",
        "R6_reduction_eligibility: PASS_INITIAL",
        "R7_parallel_layout: PASS_INITIAL",
        "R7_semantic_facade: PASS_INITIAL",
        "R7_reference_oracles: PASS_INITIAL",
        "R7_manifest_index: PASS_INITIAL",
        "R7_public_api_baseline: PASS_INITIAL",
        "R7_physical_requalification_boundary: PASS_INITIAL",
    ]
    for gate in required:
        assert gate in text, gate


def test_r7_cutover_audit_does_not_authorize_production_move_or_deletion():
    text = (REPO / "architecture" / "cutover_eligibility.yaml").read_text(encoding="utf-8")
    layout = (REPO / "architecture" / "r7_layout.yaml").read_text(encoding="utf-8")

    assert "parallel_target_layout_qualified: true" in text
    assert "staged_cutover_planning_eligible: true" in text
    assert "production_cutover_authorized: false" in text
    assert "deletion_candidates: 0" in text
    assert "production_moves: false" in layout
    assert "production_deletions: false" in layout


def test_r7_cutover_includes_a3_p1_p5_and_keeps_a4_unqualified():
    text = (REPO / "architecture" / "cutover_eligibility.yaml").read_text(encoding="utf-8")

    assert "A3_ADAPTIVE_COMPUTE_EFFICIENCY" in text
    assert "POLICY_ORCHESTRATOR_P1_P5" in text
    assert "all_13_policy_invariants_must_remain_mapped: true" in text
    assert "A4_ONTOLOGY_ADAPTATION" in text
    assert "a4_must_remain_unqualified_until_explicit_campaign: true" in text


def test_r7_cutover_preserves_physical_evidence_boundary():
    text = (REPO / "architecture" / "cutover_eligibility.yaml").read_text(encoding="utf-8")
    physical = (REPO / "architecture" / "PHYSICAL_REQUALIFICATION_MAP.yaml").read_text(encoding="utf-8")

    assert "physical_claims_must_be_requalified_when_triggered: true" in text
    assert "no_silent_evidence_upgrade: true" in text
    assert "fresh_physical_run_required_now: false" in physical
