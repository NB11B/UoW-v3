"""Comprehensive Protocol Conformance Suite for uow.magazine.v1 & uow.inference.v1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import pytest

from src.uow.magazine.schema import (
    CapabilityManifest,
    AdapterLifecycleState,
    TrainingLineage,
)
from src.uow.magazine.verification import ManifestVerifier
from src.uow.magazine.compatibility import CompatibilityChecker
from src.uow.magazine.registry import CapabilityRegistry
from src.uow.magazine.residency import ResidencyPool
from src.uow.magazine.scheduler import SerializedWorkerQueue
from src.uow.magazine.rollback import AdapterTransactionGuard, RollbackError
from src.uow.magazine.manager import MagazineManager, MagazineRuntimeError
from src.uow.inference.request_context import (
    InferenceRequest,
    InferenceResponse,
    CapabilityTarget,
    StateReference,
)
from src.uow.inference.model_backend import MockModelBackend
from src.uow.inference.output_validation import ProposalOutputValidator
from src.uow.inference.routing import CapabilityRouter, RoutingResolutionError
from src.uow.inference.gateway import InferenceGateway


@pytest.fixture
def temp_adapter_fixture(tmp_path: Path):
    """Creates a temporary verified adapter file and manifest."""
    adapter_dir = tmp_path / "test_industrial_operational"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    weight_file = adapter_dir / "adapter_model.safetensors"
    content = b"TEST_LORA_WEIGHTS_CONTENT_V1"
    weight_file.write_bytes(content)
    actual_sha = hashlib.sha256(content).hexdigest()

    manifest = CapabilityManifest(
        manifest_version="uow.magazine.v1",
        adapter_id="test_industrial_operational",
        domain="industrial",
        grammar="operational",
        version="1.0.0",
        foundation_model="HuggingFaceTB/SmolLM2-135M-Instruct",
        foundation_revision="12fd25f773",
        adapter_sha256=actual_sha,
        weight_size_bytes=len(content),
        target_schema="uow.operational.v1",
        target_modules=["q_proj", "v_proj"],
        rank=8,
        alpha=16,
    )
    return adapter_dir, weight_file, manifest, actual_sha


# --- 1. Manifest and Cryptographic Verification Vectors ---

def test_manifest_cryptographic_verification_success(temp_adapter_fixture):
    adapter_dir, _, manifest, _ = temp_adapter_fixture
    is_valid, err = ManifestVerifier.verify_adapter(manifest, adapter_dir)
    assert is_valid is True
    assert err is None


def test_manifest_digest_mismatch_fails_closed(temp_adapter_fixture):
    adapter_dir, _, manifest, _ = temp_adapter_fixture
    bad_manifest = CapabilityManifest(
        **{**manifest.to_dict(), "adapter_sha256": "0000000000000000000000000000000000000000000000000000000000000000"}
    )
    is_valid, err = ManifestVerifier.verify_adapter(bad_manifest, adapter_dir)
    assert is_valid is False
    assert "digest mismatch" in err


def test_manifest_missing_weight_artifact_fails_closed(tmp_path: Path):
    empty_dir = tmp_path / "empty_adapter"
    empty_dir.mkdir()
    manifest = CapabilityManifest(
        adapter_id="missing_weights",
        domain="industrial",
        grammar="operational",
        foundation_model="SmolLM2-135M",
        adapter_sha256="abc",
    )
    is_valid, err = ManifestVerifier.verify_adapter(manifest, empty_dir)
    assert is_valid is False
    assert "Weight artifact not found" in err


# --- 2. Compatibility Vectors ---

def test_foundation_compatibility_rejection():
    manifest = CapabilityManifest(
        adapter_id="incompat_adapter",
        domain="industrial",
        grammar="operational",
        foundation_model="HuggingFaceTB/SmolLM2-135M-Instruct",
        adapter_sha256="abc",
    )
    # Attempt to load against Pythia
    is_compat, reason = CompatibilityChecker.check_compatibility(
        manifest=manifest,
        foundation_id="EleutherAI/pythia-160m",
        foundation_architecture="GPTNeoXForCausalLM",
    )
    assert is_compat is False
    assert "Foundation mismatch" in reason


def test_target_module_compatibility_rejection():
    manifest = CapabilityManifest(
        adapter_id="target_incompat",
        domain="industrial",
        grammar="operational",
        foundation_model="HuggingFaceTB/SmolLM2-135M-Instruct",
        adapter_sha256="abc",
        target_modules=["invalid_custom_projection"],
    )
    is_compat, reason = CompatibilityChecker.check_compatibility(
        manifest=manifest,
        foundation_id="HuggingFaceTB/SmolLM2-135M-Instruct",
        foundation_architecture="LlamaForCausalLM",
        available_module_names=["q_proj", "v_proj", "k_proj", "o_proj"],
    )
    assert is_compat is False
    assert "Target module incompatible" in reason


# --- 3. Lifecycle State Machine Vectors ---

def test_lifecycle_fsm_transitions(temp_adapter_fixture):
    adapter_dir, _, manifest, _ = temp_adapter_fixture
    backend = MockModelBackend()
    manager = MagazineManager(
        foundation_id="HuggingFaceTB/SmolLM2-135M-Instruct",
        foundation_revision="12fd25f773",
        foundation_architecture="LlamaForCausalLM",
        backend_loader=backend.load_adapter,
        backend_switcher=backend.switch_adapter,
        backend_unloader=backend.unload_adapter,
    )

    # 1. Register & Verify
    state = manager.register_manifest(manifest, adapter_dir, auto_verify=True)
    assert state == AdapterLifecycleState.VERIFIED

    # 2. Load
    manager.load_adapter(manifest.adapter_id)
    assert manager.registry.get_lifecycle_state(manifest.adapter_id) == AdapterLifecycleState.LOADED

    # 3. Active
    manager.switch_adapter(manifest.adapter_id)
    assert manager.registry.get_lifecycle_state(manifest.adapter_id) == AdapterLifecycleState.ACTIVE
    assert manager.residency.active_adapter_id == manifest.adapter_id


# --- 4. Residency and LRU Eviction Vectors ---

def test_residency_lru_eviction(tmp_path: Path):
    pool = ResidencyPool(max_resident_slots=3)

    # Load 3 adapters
    pool.register_loaded("adapter_1")
    pool.register_loaded("adapter_2")
    pool.register_loaded("adapter_3")
    assert pool.resident_count == 3

    # Mark adapter_1 as active
    pool.mark_active("adapter_1")

    # Access adapter_3 so adapter_2 becomes the LRU
    pool.register_loaded("adapter_3")

    # Load adapter_4 -> adapter_2 should be evicted (adapter_1 is active, adapter_3 was recently accessed)
    evicted = pool.register_loaded("adapter_4")
    assert evicted == "adapter_2"
    assert pool.is_resident("adapter_2") is False
    assert pool.is_resident("adapter_1") is True
    assert pool.is_resident("adapter_3") is True
    assert pool.is_resident("adapter_4") is True


# --- 5. Request-Level Isolation Vectors ---

def test_serialized_worker_queue_isolation():
    queue = SerializedWorkerQueue()
    execution_order = []

    def task(req_id: str, delay: float):
        def _run():
            execution_order.append(f"start_{req_id}")
            time.sleep(delay)
            execution_order.append(f"end_{req_id}")
            return req_id
        return queue.execute_transaction(req_id, _run)

    # Launch two concurrent threads
    t1 = threading.Thread(target=task, args=("req_1", 0.05))
    t2 = threading.Thread(target=task, args=("req_2", 0.01))

    t1.start()
    time.sleep(0.005)  # Ensure t1 acquires queue first
    t2.start()

    t1.join()
    t2.join()

    # Invariants: Transactions must not interleave
    # Expected: start_req_1 -> end_req_1 -> start_req_2 -> end_req_2
    assert execution_order == ["start_req_1", "end_req_1", "start_req_2", "end_req_2"]
    assert queue.total_transactions_executed == 2


# --- 6. Atomic Rollback Vectors ---

def test_atomic_transaction_rollback_on_failure():
    switched_to = []

    def mock_switcher(target: str) -> float:
        switched_to.append(target)
        if target == "faulty_adapter":
            raise RuntimeError("Hardware switch timeout simulation")
        return 1.5

    quarantined = {}

    def mock_quarantine(aid: str, reason: str):
        quarantined[aid] = reason

    # Case: Switch to faulty adapter should trigger rollback to previous adapter
    guard = AdapterTransactionGuard(
        switch_func=mock_switcher,
        target_adapter_id="faulty_adapter",
        previous_adapter_id="safe_adapter",
        on_error_quarantine=mock_quarantine,
    )

    with pytest.raises(RuntimeError):
        with guard:
            pass

    assert "faulty_adapter" in quarantined
    assert "safe_adapter" in switched_to
    # Ensure rollback switched back to safe_adapter
    assert switched_to[-1] == "safe_adapter"


# --- 7. Inference Gateway and Output Validation Vectors ---

def test_inference_gateway_proposal_execution(temp_adapter_fixture):
    adapter_dir, _, manifest, _ = temp_adapter_fixture
    valid_proposal_json = (
        '{"domain": "industrial", "action": "EMERGENCY_DEPRESSURIZE", '
        '"disposition": "COMMIT", "parameters": {"unit_id": "P-101"}, '
        '"guard_conditions": ["interlock_verified"], "unknowns": []}'
    )

    backend = MockModelBackend(response_templates={manifest.adapter_id: valid_proposal_json})
    manager = MagazineManager(
        foundation_id=manifest.foundation_model,
        foundation_revision=manifest.foundation_revision,
        foundation_architecture="LlamaForCausalLM",
        backend_loader=backend.load_adapter,
        backend_switcher=backend.switch_adapter,
    )
    manager.register_manifest(manifest, adapter_dir)

    gateway = InferenceGateway(magazine_manager=manager, model_backend=backend)

    req = InferenceRequest(
        request_id="req-test-001",
        state=StateReference(state_hash="state_abc", sequence=1),
        capability=CapabilityTarget(domain="industrial", grammar="operational"),
        input_data={"signal": "High pressure alarm at Hydrocracker unit"},
    )

    resp = gateway.process_request(req)
    assert resp.status == "OK"
    assert resp.result is not None
    assert resp.result.proposal_type == "PROPOSAL"
    assert resp.result.grammar == "operational"
    assert resp.result.payload["action"] == "EMERGENCY_DEPRESSURIZE"
    assert resp.result.confidence_status == "UNVERIFIED"
    assert resp.result.requires_certification is True
    assert resp.provenance["adapter_id"] == manifest.adapter_id
    assert resp.provenance["adapter_sha256"] == manifest.adapter_sha256


def test_inference_gateway_ambiguous_request_fails_closed(temp_adapter_fixture):
    adapter_dir, _, manifest, _ = temp_adapter_fixture
    backend = MockModelBackend()
    manager = MagazineManager(
        foundation_id=manifest.foundation_model,
        foundation_revision=manifest.foundation_revision,
        foundation_architecture="LlamaForCausalLM",
    )
    manager.register_manifest(manifest, adapter_dir)
    gateway = InferenceGateway(magazine_manager=manager, model_backend=backend)

    # Request with ambiguous/unrecognized domain signal and no explicit capability
    req = InferenceRequest(
        request_id="req-ambiguous",
        input_data={"signal": "Some generic message without domain keywords"},
    )

    resp = gateway.process_request(req)
    assert resp.status == "CLARIFICATION_REQUIRED"
    assert "Ambiguous or unknown work request" in resp.error_message


def test_inference_gateway_schema_violation_fails_closed(temp_adapter_fixture):
    adapter_dir, _, manifest, _ = temp_adapter_fixture
    # Malformed proposal missing 'disposition' and 'parameters'
    malformed_json = '{"domain": "industrial", "action": "EMERGENCY_DEPRESSURIZE"}'

    backend = MockModelBackend(response_templates={manifest.adapter_id: malformed_json})
    manager = MagazineManager(
        foundation_id=manifest.foundation_model,
        foundation_revision=manifest.foundation_revision,
        foundation_architecture="LlamaForCausalLM",
        backend_loader=backend.load_adapter,
        backend_switcher=backend.switch_adapter,
    )
    manager.register_manifest(manifest, adapter_dir)
    gateway = InferenceGateway(magazine_manager=manager, model_backend=backend)

    req = InferenceRequest(
        request_id="req-malformed",
        capability=CapabilityTarget(domain="industrial", grammar="operational"),
        input_data={"signal": "High pressure alarm at Hydrocracker unit"},
    )

    resp = gateway.process_request(req)
    assert resp.status == "REJECTED"
    assert "Missing operational schema keys" in resp.error_message
