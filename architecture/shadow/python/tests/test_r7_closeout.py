from pathlib import Path


REPO = Path(__file__).resolve().parents[4]


def test_r7_closeout_is_frozen_additive_reference_not_cutover():
    status = (REPO / "architecture" / "reconstruction_status.yaml").read_text(encoding="utf-8")

    assert 'mode: frozen-additive-reference' in status
    assert 'R7_repository_reorganization: COMPLETE_ADDITIVE_INITIAL' in status
    assert 'production_cutover_performed: false' in status
    assert 'production_cutover_authorized: false' in status
    assert 'next_branch_required_for_relocation: true' in status
    assert 'status: FROZEN_REDUCTION_REFERENCE' in status


def test_r7_closeout_preserves_reference_oracle_distinction():
    status = (REPO / "architecture" / "reconstruction_status.yaml").read_text(encoding="utf-8")

    assert "A3_ADAPTIVE_COMPUTE_EFFICIENCY" in status
    assert "POLICY_ORCHESTRATOR_P1_P5" in status
    assert "A4_ONTOLOGY_ADAPTATION" in status
    assert "conceptual_unqualified:" in status


def test_r7_closeout_has_no_delete_candidates():
    status = (REPO / "architecture" / "reconstruction_status.yaml").read_text(encoding="utf-8")
    assert "deletion_candidates: 0" in status
