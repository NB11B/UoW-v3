"""uow.magazine package: Capability Magazine Specification and Runtime."""
from uow.magazine.schema import (
    AdapterLifecycleState,
    CapabilityManifest,
    TrainingLineage,
)
from uow.magazine.verification import ManifestVerifier, VerificationError
from uow.magazine.compatibility import CompatibilityChecker
from uow.magazine.registry import CapabilityRegistry
from uow.magazine.residency import ResidencyPool
from uow.magazine.rollback import AdapterTransactionGuard, RollbackError
from uow.magazine.provenance import ProposalProvenance
from uow.magazine.scheduler import SerializedWorkerQueue
from uow.magazine.manager import MagazineManager, MagazineRuntimeError

__all__ = [
    "AdapterLifecycleState",
    "CapabilityManifest",
    "TrainingLineage",
    "ManifestVerifier",
    "VerificationError",
    "CompatibilityChecker",
    "CapabilityRegistry",
    "ResidencyPool",
    "AdapterTransactionGuard",
    "RollbackError",
    "ProposalProvenance",
    "SerializedWorkerQueue",
    "MagazineManager",
    "MagazineRuntimeError",
]
