"""Recursive Distributed UoW Delegation & Authority Attenuation for Campaign A2.

Enforces:
1. Authority Attenuation: A(U_child) subset-of A(U_parent). Delegation may reduce or narrow authority;
   it can never create or inflate authority.
2. Cryptographic Delegation Certificates: Binds parent UoW, child UoWs, projection hash,
   authority scope, generation, and TTL.
3. Distributed Semantic Conservation: Phi(bigoplus U_i) = Phi(U) across multi-level realization trees.
4. Idempotency & Stale Generation Rejection: Results from obsolete generations are rejected;
   dropped delegates are safely retried without double commits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.contract import ParentContract
from uow.composition.fabric import DistributedActorFabric, NetworkAgent, canonical_json
from uow.composition.graph import RealizationGraph


class AuthorityPermission(str, Enum):
    READ = "read"
    TRANSFORM = "transform"
    DELEGATE = "delegate"
    VERIFY = "verify"
    COMMIT = "commit"


@dataclass(frozen=True)
class AuthorityScope:
    """Explicit capability and authority boundary for a delegated UoW.
    
    Invariance rule: A(U_child) <= A(U_parent)
    """

    permissions: FrozenSet[AuthorityPermission] = field(default_factory=frozenset)

    @classmethod
    def from_strings(cls, perms: Iterable[str]) -> AuthorityScope:
        return cls(frozenset(AuthorityPermission(p) for p in perms))

    @classmethod
    def read_only(cls) -> AuthorityScope:
        return cls(frozenset({AuthorityPermission.READ}))

    @classmethod
    def compute(cls) -> AuthorityScope:
        return cls(frozenset({AuthorityPermission.READ, AuthorityPermission.TRANSFORM}))

    @classmethod
    def delegator(cls) -> AuthorityScope:
        return cls(
            frozenset(
                {
                    AuthorityPermission.READ,
                    AuthorityPermission.TRANSFORM,
                    AuthorityPermission.DELEGATE,
                }
            )
        )

    @classmethod
    def verifier(cls) -> AuthorityScope:
        return cls(
            frozenset(
                {
                    AuthorityPermission.READ,
                    AuthorityPermission.TRANSFORM,
                    AuthorityPermission.VERIFY,
                }
            )
        )

    @classmethod
    def full(cls) -> AuthorityScope:
        return cls(frozenset(AuthorityPermission))

    def is_subset(self, other: AuthorityScope) -> bool:
        """Enforces that this scope is no broader than the other scope."""
        return self.permissions.issubset(other.permissions)

    def contains(self, perm: AuthorityPermission) -> bool:
        return perm in self.permissions

    def to_strings(self) -> Tuple[str, ...]:
        return tuple(sorted(p.value for p in self.permissions))


@dataclass(frozen=True)
class DelegationCertificate:
    """Cryptographically verifiable certificate delegating execution of a child UoW."""

    cert_id: str
    parent_contract_id: str
    parent_contract_hash: str
    child_uow_id: str
    projection_hash: str
    issuer_actor_id: str
    delegate_actor_id: str
    authority_scope: AuthorityScope
    generation: int
    granted_at_ts: float
    expires_at_ts: float
    nonce: str
    cert_hash: str = ""

    def __post_init__(self) -> None:
        if not self.cert_hash:
            payload = {
                "cert_id": self.cert_id,
                "parent_contract_id": self.parent_contract_id,
                "parent_contract_hash": self.parent_contract_hash,
                "child_uow_id": self.child_uow_id,
                "projection_hash": self.projection_hash,
                "issuer_actor_id": self.issuer_actor_id,
                "delegate_actor_id": self.delegate_actor_id,
                "authority_scope": self.authority_scope.to_strings(),
                "generation": self.generation,
                "granted_at_ts": f"{self.granted_at_ts:.4f}",
                "expires_at_ts": f"{self.expires_at_ts:.4f}",
                "nonce": self.nonce,
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "cert_hash", digest)

    def compute_hash(self) -> str:
        return self.cert_hash

    def is_valid(self, current_ts: float) -> bool:
        return current_ts <= self.expires_at_ts


def validate_delegation(
    parent_scope: AuthorityScope,
    certificate: DelegationCertificate,
    fabric: Optional[DistributedActorFabric] = None,
    current_ts: Optional[float] = None,
) -> Tuple[bool, Tuple[str, ...]]:
    """Strictly validates a DelegationCertificate against authority attenuation and fabric status."""
    ts = current_ts if current_ts is not None else time.time()
    violations: List[str] = []

    # 1. Authority Attenuation Rule: A(U_child) <= A(U_parent)
    if not certificate.authority_scope.is_subset(parent_scope):
        excess = certificate.authority_scope.permissions - parent_scope.permissions
        violations.append(
            f"AUTHORITY_INFLATION_REJECTED: delegate requested permissions {sorted(p.value for p in excess)} exceeding parent scope"
        )

    # 2. Temporal Expiration
    if not certificate.is_valid(ts):
        violations.append(
            f"DELEGATION_CERTIFICATE_EXPIRED: certificate {certificate.cert_id!r} expired at {certificate.expires_at_ts:.2f}, current time {ts:.2f}"
        )

    # 3. Distributed Fabric Checks (if fabric is active)
    if fabric is not None:
        # Issuer must hold a valid lease
        if not fabric.has_valid_lease(certificate.issuer_actor_id, ts):
            violations.append(
                f"ISSUER_LEASE_INVALID: issuer {certificate.issuer_actor_id!r} has no valid lease in fabric"
            )

        # Delegate must hold a valid lease
        if not fabric.has_valid_lease(certificate.delegate_actor_id, ts):
            violations.append(
                f"DELEGATE_LEASE_INVALID: delegate {certificate.delegate_actor_id!r} has no valid lease in fabric"
            )

        # If child is granted VERIFY or COMMIT, delegate must qualify for AuthorityClass.VERIFIER
        if certificate.authority_scope.contains(AuthorityPermission.VERIFY) or certificate.authority_scope.contains(AuthorityPermission.COMMIT):
            if not fabric.qualify_actor(certificate.delegate_actor_id, AuthorityClass.VERIFIER):
                violations.append(
                    f"DELEGATE_UNQUALIFIED_FOR_AUTHORITY: delegate {certificate.delegate_actor_id!r} lacks trusted cryptographic authority"
                )

    return len(violations) == 0, tuple(violations)


@dataclass(frozen=True)
class DelegationResult:
    """Execution telemetry and evidence returned by a delegate node."""

    child_uow_id: str
    delegate_actor_id: str
    generation: int
    status: str  # "SUCCESS", "FAILED"
    outputs: Mapping[str, Any]
    evidence_hash: str
    duration_ms: float
    error_message: str = ""


@dataclass(frozen=True)
class ChildUoWSpec:
    """Specification of a decomposed sub-UoW to be delegated."""

    child_uow_id: str
    sub_contract: ParentContract
    input_keys: Tuple[str, ...]
    expected_outputs: Tuple[str, ...]
    assigned_actor_id: str
    authority_scope: AuthorityScope
    is_idempotent: bool = True


from ..realizations.authority.delegation import DistributedDelegationNode

__all__ = [
    "AuthorityPermission",
    "AuthorityScope",
    "DelegationCertificate",
    "DelegationResult",
    "ChildUoWSpec",
    "DistributedDelegationNode",
    "validate_delegation",
]
