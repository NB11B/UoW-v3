"""Unit and conformance tests for Universal Capability Registry (WP02)."""
import hashlib
from pathlib import Path
import pytest

from uow.protocol.v1 import (
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityPackageManifest,
    QualificationStatus,
)
from uow.capabilities import (
    CapabilityLifecycleState,
    CapabilityNotFoundError,
    CapabilityQuarantinedError,
    DependencyUnsatisfiedError,
    LocalPackageStore,
    PackageVerificationError,
    UniversalCapabilityRegistry,
)


@pytest.fixture
def temp_store(tmp_path):
    return LocalPackageStore(tmp_path)


@pytest.fixture
def registry(temp_store):
    return UniversalCapabilityRegistry(store=temp_store)


def test_deterministic_capability_registration_and_invocation(registry):
    """Verify registration and direct execution of exact deterministic code."""
    desc = CapabilityDescriptor(
        capability_id="sensor.signal_filter",
        version="1.0.0",
        kind=CapabilityKind.DETERMINISTIC,
        input_contract="uow.sensor.raw.v1",
        output_contract="uow.sensor.filtered.v1",
        qualification_status=QualificationStatus.QUALIFIED,
    )

    def filter_handler(payload):
        raw = payload.get("reading", 0.0)
        return {"filtered": round(raw * 0.95, 2), "status": "NOMINAL"}

    record = registry.register_deterministic(desc, filter_handler)
    assert record.is_invokable is True

    result = registry.invoke_deterministic("sensor.signal_filter", {"reading": 100.0})
    assert result == {"filtered": 95.0, "status": "NOMINAL"}


def test_quarantine_blocks_invocation(registry):
    """Verify that quarantining a capability immediately halts execution."""
    desc = CapabilityDescriptor(
        capability_id="control.pump_cutoff",
        version="1.0.0",
        kind=CapabilityKind.DETERMINISTIC,
        input_contract="uow.pump.v1",
        output_contract="uow.pump.v1",
        qualification_status=QualificationStatus.QUALIFIED,
    )
    registry.register_deterministic(desc, lambda p: {"cutoff": True})

    # Pre-quarantine: works
    assert registry.invoke_deterministic("control.pump_cutoff", {}) == {"cutoff": True}

    # Quarantine
    registry.quarantine("control.pump_cutoff", reason="Safety boundary violation in qualification test")

    # Post-quarantine: must raise
    with pytest.raises(CapabilityQuarantinedError):
        registry.invoke_deterministic("control.pump_cutoff", {})


def test_version_rollback(registry):
    """Verify atomic rollback to previous non-quarantined version."""
    desc_v1 = CapabilityDescriptor(
        capability_id="calc.transform",
        version="1.0.0",
        kind=CapabilityKind.DETERMINISTIC,
        input_contract="v1",
        output_contract="v1",
    )
    registry.register_deterministic(desc_v1, lambda p: {"mult": p["x"] * 2})

    # Upgrade to v2
    desc_v2 = CapabilityDescriptor(
        capability_id="calc.transform",
        version="2.0.0",
        kind=CapabilityKind.DETERMINISTIC,
        input_contract="v2",
        output_contract="v2",
    )
    registry.register_deterministic(desc_v2, lambda p: {"mult": p["x"] * 10})

    assert registry.invoke_deterministic("calc.transform", {"x": 5}) == {"mult": 50}

    # Quarantine v2 and rollback to v1
    registry.quarantine("calc.transform", "Regression detected in multiplier")
    restored = registry.rollback("calc.transform", target_version="1.0.0")

    assert restored.version == "1.0.0"
    assert registry.invoke_deterministic("calc.transform", {"x": 5}) == {"mult": 10}


def test_package_installation_with_hash_verification(registry, tmp_path):
    """Verify package installation with physical artifact SHA-256 verification."""
    # Create sample artifact file
    art_file = tmp_path / "model_weights.bin"
    art_file.write_bytes(b"EXACT_MODEL_WEIGHT_BYTES_12345")
    expected_hash = hashlib.sha256(b"EXACT_MODEL_WEIGHT_BYTES_12345").hexdigest()

    manifest = CapabilityPackageManifest(
        package_id="domain.industrial.adapter",
        version="1.0.0",
        name="Industrial Domain Adapter",
        kind=CapabilityKind.NEURAL_INTERPRETER,
        capabilities=[
            CapabilityDescriptor(
                capability_id="industrial.recovery.v1",
                version="1.0.0",
                kind=CapabilityKind.NEURAL_INTERPRETER,
                input_contract="uow.recovery.request.v1",
                output_contract="uow.recovery.proposal.v1",
            )
        ],
        artifacts={"weights/recovery.bin": expected_hash},
        dependencies=[],
    )

    records = registry.install_package(
        manifest,
        artifact_files={"weights/recovery.bin": art_file},
    )
    assert len(records) == 1
    assert registry.get("industrial.recovery.v1") is not None


def test_package_hash_mismatch_rejected(registry, tmp_path):
    """Verify corrupted artifact triggers PackageVerificationError."""
    art_file = tmp_path / "corrupt.bin"
    art_file.write_bytes(b"WRONG_BYTES")

    manifest = CapabilityPackageManifest(
        package_id="domain.corrupt",
        version="1.0.0",
        kind=CapabilityKind.NEURAL_INTERPRETER,
        capabilities=[],
        artifacts={"weights/corrupt.bin": "0000000000000000000000000000000000000000000000000000000000000000"},
    )

    with pytest.raises(PackageVerificationError):
        registry.install_package(manifest, artifact_files={"weights/corrupt.bin": art_file})


def test_unsatisfied_dependency_rejected(registry):
    """Verify package cannot be installed if its dependencies are missing."""
    manifest = CapabilityPackageManifest(
        package_id="extension.specialist",
        version="1.0.0",
        kind=CapabilityKind.NEURAL_INTERPRETER,
        capabilities=[],
        dependencies=["missing.base.package.v1"],
    )

    with pytest.raises(DependencyUnsatisfiedError):
        registry.install_package(manifest)
