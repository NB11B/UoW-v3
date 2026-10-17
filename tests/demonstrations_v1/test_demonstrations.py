"""Integration test suite executing all 5 Product Acceptance Demonstrations (D1 - D5)."""
import pytest
from demonstrations.platform_demonstrations import DemonstrationRunner


@pytest.fixture
def runner(tmp_path):
    return DemonstrationRunner(output_dir=tmp_path)


def test_demonstration_d1(runner):
    res = runner.run_d1_dynamic_installation()
    assert res["success"] is True
    assert res["disposition"] == "COMMITTED"
    assert res["action"] == "trip_feeder"


def test_demonstration_d2(runner):
    res = runner.run_d2_authorized_mixed_workflow()
    assert res["success"] is True
    assert res["disposition"] == "COMMITTED"
    assert res["ledger_integrity"] is True


def test_demonstration_d3(runner):
    res = runner.run_d3_hot_upgrade_and_rollback()
    assert res["success"] is True
    assert res["rollback_version"] == "1.1.0"


def test_demonstration_d4(runner):
    res = runner.run_d4_distributed_nodes_and_recovery()
    assert res["success"] is True
    assert res["partition_handled"] is True
    assert res["replay_blocked"] is True


def test_demonstration_d5(runner):
    res = runner.run_d5_new_expertise_lifecycle()
    assert res["success"] is True
    assert res["grounding_valid"] is True
    assert res["hallucination_intercepted"] is True


def test_run_all_demonstrations(runner):
    all_res = runner.run_all()
    assert all_res["all_demonstrations_passed"] is True
