"""Unit and conformance tests for Magazine Deployment & Domain Engine (WP03, WP04)."""
import pytest
from src.uow.protocol.v1 import (
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityProposal,
    QualificationStatus,
    WorkRequest,
)
from src.uow.capabilities import UniversalCapabilityRegistry
from src.uow.magazine.deployment import DeploymentMode, MagazineDeploymentEngine
from src.uow.expertise.domain import (
    DomainContextCompiler,
    DomainGroundingValidator,
    build_industrial_domain_package,
)


@pytest.fixture
def ind_pkg():
    return build_industrial_domain_package()


def test_domain_context_compilation(ind_pkg):
    """Verify context compiler produces structured, grounded context without memorized weights."""
    compiler = DomainContextCompiler(ind_pkg)
    prompt = compiler.compile_prompt(
        grammar="operational",
        work_payload={"event": "high_pressure_alert", "sensor": "PUMP_101", "pressure": 195.4},
        pre_state={"system_mode": "ACTIVE"},
    )
    assert "You are the deterministic UoW Grounded Operational Proposer" in prompt
    assert "Domain ID: domain.industrial.v1" in prompt
    assert "PUMP_101" in prompt
    assert "isolate_pump" in prompt
    assert "Never fabricate entity identifiers" in prompt


def test_domain_grounding_valid_proposal(ind_pkg):
    """Verify validation passes when actions and entities are fully grounded."""
    validator = DomainGroundingValidator(ind_pkg)
    result = validator.validate(
        proposed_action="isolate_pump",
        bindings={"pump_id": "PUMP_101", "isolation_valve_id": "VALVE_201"},
    )
    assert result.is_valid is True
    assert len(result.grounding_violations) == 0


def test_domain_grounding_alias_resolution(ind_pkg):
    """Verify validator resolves colloquial aliases to canonical entity IDs."""
    validator = DomainGroundingValidator(ind_pkg)
    result = validator.validate(
        proposed_action="isolate_pump",
        bindings={"pump_id": "P-101", "isolation_valve_id": "V-201"},
    )
    assert result.is_valid is True
    assert result.resolved_bindings["pump_id"] == "PUMP_101"
    assert result.resolved_bindings["isolation_valve_id"] == "VALVE_201"


def test_domain_grounding_fabrication_rejection(ind_pkg):
    """Verify validator rejects ungrounded or fabricated entity identifiers."""
    validator = DomainGroundingValidator(ind_pkg)
    result = validator.validate(
        proposed_action="isolate_pump",
        bindings={"pump_id": "PUMP_999_HALLUCINATED", "isolation_valve_id": "VALVE_201"},
    )
    assert result.is_valid is False
    assert any("Fabricated or ungrounded entity identifier" in v for v in result.grounding_violations)


def test_domain_grounding_safety_guard_violation(ind_pkg):
    """Verify safety guards intercept parameter values exceeding thresholds."""
    validator = DomainGroundingValidator(ind_pkg)
    result = validator.validate(
        proposed_action="vent_pressure",
        bindings={"valve_id": "VALVE_201", "target_pressure": 250.0},  # Max allowed is 180.0
    )
    assert result.is_valid is False
    assert any("exceeds ceiling 180.0" in v for v in result.safety_violations)


def test_magazine_deployment_multi_strategy():
    """Verify unified execution engine across deterministic, neural, and remote strategies."""
    registry = UniversalCapabilityRegistry()

    # 1. Deterministic capability
    det_desc = CapabilityDescriptor(
        capability_id="det.exact_calc",
        version="1.0.0",
        kind=CapabilityKind.DETERMINISTIC,
        input_contract="v1",
        output_contract="v1",
        qualification_status=QualificationStatus.QUALIFIED,
    )
    registry.register_deterministic(det_desc, lambda p: {"action": "exact_compute", "bindings": {"res": p["v"] * 2}})

    # 2. Neural capability
    neural_desc = CapabilityDescriptor(
        capability_id="neural.recovery",
        version="1.0.0",
        kind=CapabilityKind.NEURAL_INTERPRETER,
        input_contract="v1",
        output_contract="v1",
        qualification_status=QualificationStatus.QUALIFIED,
    )
    registry.register_neural(neural_desc)

    def mock_generator(cap_id, prompt):
        return '{"action": "isolate_pump", "bindings": {"pump_id": "PUMP_101"}, "uncertainty": 0.02}'

    def mock_remote_dispatcher(cap_id, req):
        return CapabilityProposal(
            proposal_id=f"remote-{req.work_id}",
            work_id=req.work_id,
            producer_identity="peer-node-nano",
            capability_id=cap_id,
            proposed_action="remote_action",
            bindings={"node": "nano"},
        )

    engine = MagazineDeploymentEngine(
        registry=registry,
        neural_generator=mock_generator,
        remote_dispatcher=mock_remote_dispatcher,
    )

    req1 = WorkRequest(
        work_id="w-1",
        origin_node="host",
        state_reference="s0",
        requested_capability="det.exact_calc",
        payload={"v": 21},
    )
    prop1 = engine.execute_capability("det.exact_calc", req1)
    assert prop1.proposed_action == "exact_compute"
    assert prop1.bindings["res"] == 42
    assert prop1.evidence["execution_mode"] == "deterministic_substitute"

    # Neural resident execution
    req2 = WorkRequest(
        work_id="w-2",
        origin_node="host",
        state_reference="s0",
        requested_capability="neural.recovery",
        payload={"alert": "overheat"},
    )
    prop2 = engine.execute_capability("neural.recovery", req2)
    assert prop2.proposed_action == "isolate_pump"
    assert prop2.bindings["pump_id"] == "PUMP_101"
    assert prop2.uncertainty_score == 0.02

    # Remote capability mode
    engine.set_capability_mode("neural.recovery", DeploymentMode.REMOTE_CAPABILITY)
    prop3 = engine.execute_capability("neural.recovery", req2)
    assert prop3.producer_identity == "peer-node-nano"
    assert prop3.proposed_action == "remote_action"
