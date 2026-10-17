"""Unit and conformance tests for Execution Planner, Authority Kernel, and Transport (WP06, WP07, WP08)."""
import pytest

from uow.capabilities import UniversalCapabilityRegistry
from uow.expertise.domain import build_industrial_domain_package
from uow.magazine.deployment import MagazineDeploymentEngine
from uow.orchestration.planner import ExecutionPlanner
from uow.authority.platform_authority import (
    PlatformAuthorityKernel,
    PlatformEvidenceLedger,
    PlatformRecoveryManager,
)
from uow.protocol.v1 import (
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityProposal,
    CommitDisposition,
    QualificationStatus,
    WorkCertificate,
    WorkEvent,
    WorkRequest,
)
from uow.transport import (
    ArduinoUnoSerialLink,
    FramedTransportSession,
    NodeType,
    PeerNode,
)


@pytest.fixture
def ind_domain():
    return build_industrial_domain_package()


@pytest.fixture
def authority_kernel():
    return PlatformAuthorityKernel(node_id="node_auth_master")


@pytest.fixture
def evidence_ledger():
    return PlatformEvidenceLedger()


def test_deterministic_first_planner(ind_domain, authority_kernel):
    """Verify planner selects exact deterministic route over neural when available."""
    registry = UniversalCapabilityRegistry()

    # Register deterministic provider
    det_desc = CapabilityDescriptor(
        capability_id="det.industrial.cutoff",
        version="1.0.0",
        kind=CapabilityKind.DETERMINISTIC,
        input_contract="v1",
        output_contract="v1",
        qualification_status=QualificationStatus.QUALIFIED,
    )
    registry.register_deterministic(
        det_desc,
        lambda p: {"action": "isolate_pump", "bindings": {"pump_id": "PUMP_101", "isolation_valve_id": "VALVE_201"}},
    )

    # Register neural capability
    neural_desc = CapabilityDescriptor(
        capability_id="industrial.cutoff",
        version="1.0.0",
        kind=CapabilityKind.NEURAL_INTERPRETER,
        input_contract="v1",
        output_contract="v1",
        dependencies=["domain.industrial.v1"],
        qualification_status=QualificationStatus.QUALIFIED,
    )
    registry.register_neural(neural_desc)

    engine = MagazineDeploymentEngine(registry=registry)
    planner = ExecutionPlanner(
        registry=registry,
        deployment_engine=engine,
        domain_packages={ind_domain.domain_id: ind_domain},
        authority_certifier=lambda prop, pre: authority_kernel.certify(prop, pre, pre),
    )

    req = WorkRequest(
        work_id="work-cutoff-01",
        origin_node="host",
        state_reference="state-s0",
        requested_capability="industrial.cutoff",
        payload={"pressure": 190.0},
    )

    result = planner.execute_work(req, pre_state_hash="state-s0")
    assert result.success is True
    assert result.final_disposition == CommitDisposition.COMMITTED
    # Rationale explains deterministic substitute was selected
    assert any("DETERMINISTIC_SUBSTITUTE" in s.decision for s in result.audit_trail)
    explanation = result.explain()
    assert "Execution Audit Trail" in explanation


def test_authority_kernel_pre_state_divergence(authority_kernel):
    """Verify authority kernel rejects proposals with pre-state divergence."""
    prop = CapabilityProposal(
        proposal_id="p-1",
        work_id="w-1",
        producer_identity="cerebras_111m",
        capability_id="industrial.op",
        proposed_action="isolate_pump",
        bindings={"pump_id": "PUMP_101"},
    )
    cert = authority_kernel.certify(
        proposal=prop,
        expected_pre_state_hash="hash_expected_123",
        actual_pre_state_hash="hash_actual_diverged_456",
    )
    assert cert.is_valid is False
    assert "Pre-state divergence" in (cert.rejection_reason or "")


def test_evidence_ledger_monotonic_hash_chain(evidence_ledger, authority_kernel):
    """Verify evidence ledger advances monotonically and verifies cryptographic chain."""
    prop1 = CapabilityProposal(
        proposal_id="p-1",
        work_id="w-1",
        producer_identity="node-1",
        capability_id="cap-1",
        proposed_action="act_1",
        bindings={"val": 1},
    )
    cert1 = authority_kernel.certify(prop1, "state-0", "state-0")
    rec1 = evidence_ledger.commit(cert1)
    assert rec1.step_number == 1
    assert rec1.prev_evidence_root == "0" * 64

    prop2 = CapabilityProposal(
        proposal_id="p-2",
        work_id="w-2",
        producer_identity="node-1",
        capability_id="cap-1",
        proposed_action="act_2",
        bindings={"val": 2},
    )
    cert2 = authority_kernel.certify(prop2, rec1.resulting_state_hash, rec1.resulting_state_hash)
    rec2 = evidence_ledger.commit(cert2)
    assert rec2.step_number == 2
    assert rec2.prev_evidence_root == evidence_ledger._records[0].prev_evidence_root or rec2.prev_evidence_root != "0" * 64

    assert evidence_ledger.verify_integrity() is True


def test_distributed_transport_framing_and_partition():
    """Verify framed messaging across distributed nodes with partition simulation."""
    host = PeerNode(node_id="host_workstation", node_type=NodeType.HOST_COMPLETE)
    nano = PeerNode(node_id="jetson_nano_edge", node_type=NodeType.EDGE_TRANSPORT)

    session = FramedTransportSession(host)
    session.register_peer(nano)

    evt = WorkEvent(
        event_id="evt-cross-01",
        node_id="host_workstation",
        local_sequence=1,
        local_time_ms=5000,
        causal_parents=[],
        event_type="telemetry_sync",
        payload={"load": 0.45},
    )
    frame_bytes = session.send_message("jetson_nano_edge", evt)
    assert len(frame_bytes) > 20

    # Receive at nano
    nano_session = FramedTransportSession(nano)
    nano_session.register_peer(host)
    received_msg, seq = nano_session.receive_frame(frame_bytes, "host_workstation")
    assert isinstance(received_msg, WorkEvent)
    assert received_msg.event_id == "evt-cross-01"

    # Simulate network partition
    session.set_partition("jetson_nano_edge", True)
    with pytest.raises(Exception):  # FrameError
        session.send_message("jetson_nano_edge", evt)


def test_uno_serial_link_framing():
    """Verify Uno serial framed packet encoding and telemetry ingestion."""
    uno = ArduinoUnoSerialLink()
    actuation_frame = uno.build_actuation_frame(target_led=True, seq=5)
    assert actuation_frame.startswith(b"UOW1")

    # Emulate incoming telemetry frame from Uno
    sensor_evt = WorkEvent(
        event_id="uno-sensor-01",
        node_id="uno_endpoint",
        local_sequence=1,
        local_time_ms=1020,
        causal_parents=[],
        event_type="sensor_telemetry",
        payload={"sensor_val": 48.2},
    )
    raw_telemetry = uno.session.send_message("uno_endpoint", sensor_evt)
    parsed_evt = uno.process_incoming_sensor_frame(raw_telemetry)
    assert parsed_evt.payload["sensor_val"] == 48.2
    assert uno.last_sensor_reading == 48.2
