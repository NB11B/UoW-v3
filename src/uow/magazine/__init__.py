"""uow.magazine package: Capability Magazine Specification and Runtime."""
from src.uow.magazine.schema import (
    AdapterLifecycleState,
    CapabilityManifest,
    TrainingLineage,
)
from src.uow.magazine.verification import ManifestVerifier, VerificationError
from src.uow.magazine.compatibility import CompatibilityChecker
from src.uow.magazine.registry import CapabilityRegistry
from src.uow.magazine.residency import ResidencyPool
from src.uow.magazine.rollback import AdapterTransactionGuard, RollbackError
from src.uow.magazine.provenance import ProposalProvenance
from src.uow.magazine.scheduler import SerializedWorkerQueue
from src.uow.magazine.manager import MagazineManager, MagazineRuntimeError

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
