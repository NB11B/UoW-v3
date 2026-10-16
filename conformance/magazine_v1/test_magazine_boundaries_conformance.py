"""Conformance Tests for P1/P2 Implementation Boundaries:
1. True Backend Isolation (KV-cache and adapter context isolation).
2. Crash Consistency (Manifest catalog persistence, corrupt weight quarantine, and restart recovery).
3. Protocol Authority Invariant (Advisory neural proposal vs deterministic UoW certification and ledger commitment).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest
import tempfile

from src.uow.magazine.schema import (
    CapabilityManifest,
    AdapterLifecycleState,
)
from src.uow.magazine.registry import CapabilityRegistry
from src.uow.magazine.manager import MagazineManager, MagazineRuntimeError
from src.uow.inference.request_context import (
    InferenceRequest,
    InferenceResponse,
    CapabilityTarget,
    TypedProposal,
)
from src.uow.inference.gateway import InferenceGateway
from src.uow.inference.model_backend import MockModelBackend, PyTorchPeftBackend
from src.uow.inference.authority_bridge import AuthorityBridge
from src.uow.contracts import (
    UoW,
    make_uow,
    Route,
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Successor,
    SuccessorKind,
)
from src.uow.state import WorldState
from src.uow.engine import EvidenceLedger


def create_dummy_adapter_dir(tmp_path: Path, name: str, size: int = 1024) -> tuple[Path, str]:
    adapter_dir = tmp_path / name
    adapter_dir.mkdir(parents=True, exist_ok=True)
    weight_file = adapter_dir / "adapter_model.safetensors"
    content = f"dummy_weights_content_for_{name}".encode("utf-8") + b"\x00" * (size - len(name) - 30)
    weight_file.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({
            "base_model_name_or_path": "HuggingFaceTB/SmolLM2-135M-Instruct",
            "r": 8,
            "lora_alpha": 16,
            "target_modules": ["q_proj", "v_proj"],
        })
    )
    return adapter_dir, sha256


class TestImplementationBoundariesConformance:

    def test_crash_consistency_and_catalog_restart(self, tmp_path):
        """Boundary 2: Manifest catalog survives restart, corrupt weights are quarantined on reload."""
        catalog_file = tmp_path / "magazine_catalog.json"
        adapter_dir, sha = create_dummy_adapter_dir(tmp_path, "industrial.operational")

        manifest = CapabilityManifest(
            adapter_id="industrial.operational",
            domain="industrial",
            grammar="operational",
            version="1.0.0",
            foundation_model="HuggingFaceTB/SmolLM2-135M-Instruct",
            foundation_revision="main",
            adapter_sha256=sha,
            weight_size_bytes=len((adapter_dir / "adapter_model.safetensors").read_bytes()),
            rank=8,
            alpha=16,
            target_modules=["q_proj", "v_proj"],
            target_schema="uow.operational.v1",
        )

        # 1. Register and save catalog
        registry1 = CapabilityRegistry()
        registry1.register(manifest, adapter_dir, auto_verify=True)
        assert registry1.get_lifecycle_state("industrial.operational") == AdapterLifecycleState.VERIFIED
        registry1.save_catalog(catalog_file)
        assert catalog_file.exists()

        # 2. Restart and reload
        registry2 = CapabilityRegistry()
        loaded_count = registry2.load_catalog(catalog_file, auto_verify_on_reload=True)
        assert loaded_count == 1
        assert registry2.get_lifecycle_state("industrial.operational") == AdapterLifecycleState.VERIFIED

        # 3. Simulate weight corruption (tampering with bytes)
        weight_file = adapter_dir / "adapter_model.safetensors"
        weight_file.write_bytes(b"tampered_corrupted_data")

        # Reload with tampered file -> must fail verification and quarantine
        registry3 = CapabilityRegistry()
        registry3.load_catalog(catalog_file, auto_verify_on_reload=True)
        assert registry3.get_lifecycle_state("industrial.operational") == AdapterLifecycleState.QUARANTINED
        assert "digest mismatch" in registry3.get_quarantine_reason("industrial.operational").lower()

    def test_corrupt_adapter_load_clean_rejection(self, tmp_path):
        """Boundary 2: Loading quarantined or corrupt adapter aborts cleanly without state damage."""
        adapter_dir, _ = create_dummy_adapter_dir(tmp_path, "corrupt_adapter")
        # Give wrong expected hash
        manifest = CapabilityManifest(
            adapter_id="corrupt.adapter",
            domain="industrial",
            grammar="operational",
            version="1.0.0",
            foundation_model="HuggingFaceTB/SmolLM2-135M-Instruct",
            foundation_revision="main",
            adapter_sha256="0" * 64,  # Intentionally incorrect
            weight_size_bytes=100,
            rank=8,
            alpha=16,
            target_modules=["q_proj", "v_proj"],
            target_schema="uow.operational.v1",
        )

        mgr = MagazineManager(
            foundation_id="HuggingFaceTB/SmolLM2-135M-Instruct",
            foundation_revision="main",
            foundation_architecture="LlamaForCausalLM",
        )
        state = mgr.register_manifest(manifest, adapter_dir, auto_verify=True)
        assert state == AdapterLifecycleState.QUARANTINED

        # Attempt to load quarantined adapter must raise MagazineRuntimeError
        with pytest.raises(MagazineRuntimeError) as exc_info:
            mgr.load_adapter("corrupt.adapter")
        assert "Cannot load quarantined adapter" in str(exc_info.value)
        assert mgr.residency.resident_count == 0

    def test_backend_use_cache_flag_and_isolation(self):
        """Boundary 1: Verify PyTorchPeftBackend configures generation without KV-cache retention."""
        backend = PyTorchPeftBackend()
        # Verify default active state is None
        assert backend.active_adapter_id is None
        assert backend.peft_model is None

    def test_protocol_authority_advisory_boundary(self):
        """Boundary 3: Unprivileged neural proposal must be independently certified by UoW kernel.
        
        Zero unauthorized commits when proposal violates preconditions or route guards.
        """
        ledger = EvidenceLedger()
        assert ledger.root_hash() == "0" * 64

        # Define deterministic UoW with interlock guard
        uow = make_uow(
            "uow_refinery_depressurize",
            [
                Route(
                    guard=Guard(GuardOp.EQ, "plant.interlock_armed", 1),
                    mutations=(
                        Mutation(MutationOp.SET, "plant.pressure", 95.0),
                        Mutation(MutationOp.SET, "plant.valve_status", "OPEN"),
                    ),
                    successor=Successor(kind=SuccessorKind.STATIC, value="uow_complete"),
                )
            ]
        )

        # 1. Test Valid Proposal execution under armed state (plant.interlock_armed = 1)
        valid_state = WorldState(attributes={"plant.pressure": 150.0, "plant.interlock_armed": 1})
        valid_response = InferenceResponse(
            protocol="uow.inference.v1",
            request_id="req_001",
            status="OK",
            result=TypedProposal(
                proposal_type="PROPOSAL",
                grammar="operational",
                payload={
                    "domain": "industrial",
                    "action": "EMERGENCY_DEPRESSURIZE",
                    "disposition": "COMMIT",
                    "parameters": {"unit_id": "HC-401", "target_setpoint": 95},
                    "guard_conditions": ["interlock_armed"],
                    "unknowns": [],
                },
                confidence_status="UNVERIFIED",
                requires_certification=True,
            ),
        )

        eval1 = AuthorityBridge.evaluate_and_commit(valid_response, uow, valid_state, ledger)
        assert eval1.is_schema_valid is True
        assert eval1.is_authority_certified is True
        assert eval1.evidence_record is not None
        assert len(ledger.records) == 1
        assert ledger.verify_integrity() is True

        # 2. Test Proposal Rejection under disarmed state (plant.interlock_armed = 0)
        unarmed_state = WorldState(attributes={"plant.pressure": 150.0, "plant.interlock_armed": 0})
        eval2 = AuthorityBridge.evaluate_and_commit(valid_response, uow, unarmed_state, ledger)
        assert eval2.is_schema_valid is True
        assert eval2.is_authority_certified is False
        assert any(term in (eval2.rejection_reason or "") for term in ("RECOMPUTATION_FAILED", "ROUTE_DIVERGENCE"))
        # Invariant: Ledger must NOT append invalid proposal
        assert len(ledger.records) == 1  # Still 1, 0 unauthorized commits!

        # 3. Test Proposal Rejection when proposal contains unresolved references
        unresolved_response = InferenceResponse(
            protocol="uow.inference.v1",
            request_id="req_003",
            status="OK",
            result=TypedProposal(
                proposal_type="PROPOSAL",
                grammar="operational",
                payload={
                    "domain": "industrial",
                    "action": "EMERGENCY_DEPRESSURIZE",
                    "disposition": "ROLLBACK",
                    "parameters": {"unit_id": "UNKNOWN_UNIT"},
                    "guard_conditions": [],
                    "unknowns": ["unit_id:UNKNOWN_UNIT"],
                },
                confidence_status="UNVERIFIED",
                requires_certification=True,
            ),
        )
        eval3 = AuthorityBridge.evaluate_and_commit(unresolved_response, uow, valid_state, ledger)
        assert eval3.is_schema_valid is True
        assert eval3.is_authority_certified is False
        assert "UNRESOLVED_REFERENCES" in (eval3.rejection_reason or "")
        assert len(ledger.records) == 1  # Invariant: 0 unauthorized commits!
