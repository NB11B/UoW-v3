"""Derived actor execution adapters for adaptive composition.

Actor descriptors and bindings remain semantic metadata. This module supplies the
optional execution realization that turns a qualified actor binding into an
actual call boundary.

A CertifiedRuntimeActor permits a complete AdaptiveCompositionRuntime to appear
as one actor to its parent without granting it authority over parent state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence, Tuple

from uow.composition.actor import ActorDescriptor, AuthorityClass
from uow.composition.boundary import (
    CompositionBoundaryCertificate,
    verify_composition_boundary,
)
from uow.composition.graph import RealizationNode


def _canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class ActorExecutionResult:
    """Result returned across an actor execution boundary."""

    actor_id: str
    status: str
    outputs: Mapping[str, Any]
    evidence_hash: str = ""
    child_record_hash: str = ""
    error_message: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_hash:
            payload = {
                "actor_id": self.actor_id,
                "status": self.status,
                "outputs": dict(self.outputs),
                "child_record_hash": self.child_record_hash,
                "error_message": self.error_message,
            }
            object.__setattr__(
                self,
                "evidence_hash",
                hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest(),
            )

    @property
    def ok(self) -> bool:
        return self.status == "SUCCESS"


class ActorExecutor(Protocol):
    """Execution realization for one actor identifier."""

    def execute_actor(
        self,
        *,
        actor_id: str,
        node: RealizationNode,
        inputs: Mapping[str, Any],
        current_ts: Optional[float] = None,
        ancestry: Tuple[str, ...] = (),
    ) -> ActorExecutionResult:
        ...


class ActorExecutionRegistry:
    """Runtime-only map from qualified actor identities to execution adapters."""

    def __init__(self) -> None:
        self._executors: Dict[str, ActorExecutor] = {}

    def register(self, actor_id: str, executor: ActorExecutor) -> None:
        self._executors[actor_id] = executor

    def unregister(self, actor_id: str) -> Optional[ActorExecutor]:
        return self._executors.pop(actor_id, None)

    def get(self, actor_id: str) -> Optional[ActorExecutor]:
        return self._executors.get(actor_id)

    def actor_ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._executors))


class CertifiedRuntimeActor:
    """Expose a boundary-certified UoW runtime as a parent actor.

    This adapter carries no parent mutation or commit authority. It can only
    return outputs and evidence through the node boundary. Any explicit authority
    transfer between UoWs must use the existing delegation machinery.
    """

    def __init__(
        self,
        *,
        surface_id: str,
        runtime: Any,
        boundary_certificate: CompositionBoundaryCertificate,
        output_mapping: Optional[Mapping[str, str]] = None,
    ) -> None:
        if not boundary_certificate.is_accepted:
            raise ValueError("Cannot expose a rejected composition boundary")
        if boundary_certificate.subject_id != surface_id:
            raise ValueError("Boundary subject does not match recursive surface id")
        self.surface_id = surface_id
        self.runtime = runtime
        self.boundary_certificate = boundary_certificate
        self.output_mapping = dict(output_mapping or {})

    def descriptor(
        self,
        actor_id: str,
        capabilities: Sequence[str],
        *,
        authority_class: AuthorityClass = AuthorityClass.PROPOSER_ONLY,
    ) -> ActorDescriptor:
        return ActorDescriptor(
            actor_id=actor_id,
            capabilities=tuple(sorted(set(capabilities).union({"uow:recursive"}))),
            substrate="uow_recursive",
            authority_class=authority_class,
            endpoint=f"uow://{self.surface_id}",
        )

    def execute_actor(
        self,
        *,
        actor_id: str,
        node: RealizationNode,
        inputs: Mapping[str, Any],
        current_ts: Optional[float] = None,
        ancestry: Tuple[str, ...] = (),
    ) -> ActorExecutionResult:
        if self.surface_id in ancestry:
            return ActorExecutionResult(
                actor_id=actor_id,
                status="FAILED",
                outputs={},
                error_message=f"RECURSIVE_CYCLE_DETECTED:{self.surface_id}",
            )

        valid, violations = verify_composition_boundary(
            self.boundary_certificate,
            self.runtime.active_graph,
            self.runtime.contract,
        )
        if not valid:
            return ActorExecutionResult(
                actor_id=actor_id,
                status="FAILED",
                outputs={},
                error_message="RECURSIVE_BOUNDARY_INVALID:" + ";".join(violations),
            )

        child_record = self.runtime.execute(
            inputs,
            current_ts=current_ts,
            ancestry=ancestry + (self.surface_id,),
        )
        child_hash = child_record.compute_hash()
        child_evidence = getattr(child_record, "evidence_root", "") or child_hash

        if child_record.status != "SUCCESS":
            return ActorExecutionResult(
                actor_id=actor_id,
                status="FAILED",
                outputs={},
                evidence_hash=child_evidence,
                child_record_hash=child_hash,
                error_message=f"CHILD_EXECUTION_FAILED:{child_record.error_message}",
            )

        mapped: Dict[str, Any] = {}
        for child_key, value in child_record.final_outputs.items():
            parent_key = self.output_mapping.get(child_key, child_key)
            if parent_key in node.outputs:
                mapped[parent_key] = value

        missing = set(node.outputs) - set(mapped)
        if missing:
            return ActorExecutionResult(
                actor_id=actor_id,
                status="FAILED",
                outputs=mapped,
                evidence_hash=child_evidence,
                child_record_hash=child_hash,
                error_message=f"ACTOR_OUTPUT_DEFICIT:{sorted(missing)}",
            )

        return ActorExecutionResult(
            actor_id=actor_id,
            status="SUCCESS",
            outputs=mapped,
            evidence_hash=child_evidence,
            child_record_hash=child_hash,
        )


__all__ = [
    "ActorExecutionRegistry",
    "ActorExecutionResult",
    "ActorExecutor",
    "CertifiedRuntimeActor",
]
