"""Unified Magazine Deployment Engine supporting Multi-Strategy Execution.

Comprises Subsystem S2/S3 functionality supporting:
1. Resident adapter (RAM/VRAM)
2. Paged adapter (on-demand disk paging)
3. Fixed specialist export (dedicated model/ONNX artifact)
4. Remote capability (delegation to authenticated UoW peer)
5. Deterministic substitute (exact provider bypass)
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional

from uow.capabilities import (
    CapabilityLifecycleState,
    CapabilityRecord,
    UniversalCapabilityRegistry,
)
from uow.protocol.v1 import (
    AuthorityLevel,
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityProposal,
    WorkRequest,
)
from .manager import MagazineManager, MagazineRuntimeError


class DeploymentMode(str, Enum):
    RESIDENT_ADAPTER = "resident_adapter"
    PAGED_ADAPTER = "paged_adapter"
    FIXED_SPECIALIST_EXPORT = "fixed_specialist_export"
    REMOTE_CAPABILITY = "remote_capability"
    DETERMINISTIC_SUBSTITUTE = "deterministic_substitute"


class MagazineDeploymentEngine:
    """Unified engine that transparently routes capability execution across deployment modes."""

    def __init__(
        self,
        registry: UniversalCapabilityRegistry,
        magazine_manager: Optional[MagazineManager] = None,
        default_mode: DeploymentMode = DeploymentMode.RESIDENT_ADAPTER,
        remote_dispatcher: Optional[Callable[[str, WorkRequest], CapabilityProposal]] = None,
        neural_generator: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        self.registry = registry
        self.magazine_manager = magazine_manager
        self.default_mode = default_mode
        self._remote_dispatcher = remote_dispatcher
        self._neural_generator = neural_generator
        self._capability_modes: Dict[str, DeploymentMode] = {}

    def set_capability_mode(self, capability_id: str, mode: DeploymentMode) -> None:
        """Assign an explicit deployment strategy to a specific capability."""
        self._capability_modes[capability_id] = mode

    def get_capability_mode(self, capability_id: str) -> DeploymentMode:
        """Get the active deployment strategy for a capability."""
        # If deterministic provider registered, automatically use deterministic substitute
        record = self.registry.get(capability_id)
        if record and record.kind == CapabilityKind.DETERMINISTIC:
            return DeploymentMode.DETERMINISTIC_SUBSTITUTE
        return self._capability_modes.get(capability_id, self.default_mode)

    def execute_capability(
        self,
        capability_id: str,
        work_request: WorkRequest,
        context_prompt: Optional[str] = None,
    ) -> CapabilityProposal:
        """Execute capability through the assigned deployment strategy and return a verified proposal."""
        record = self.registry.get(capability_id)
        if not record:
            raise MagazineRuntimeError(f"Capability '{capability_id}' not found in registry.")

        if not record.is_invokable:
            raise MagazineRuntimeError(
                f"Capability '{capability_id}' is not in invokable state (state: {record.state}, status: {record.descriptor.qualification_status})"
            )

        mode = self.get_capability_mode(capability_id)
        t0 = time.time()

        if mode == DeploymentMode.DETERMINISTIC_SUBSTITUTE:
            # Deterministic execution path
            raw_output = self.registry.invoke_deterministic(capability_id, work_request.payload)
            proposal = CapabilityProposal(
                proposal_id=f"prop-det-{work_request.work_id}",
                work_id=work_request.work_id,
                producer_identity=f"deterministic:{capability_id}",
                capability_id=capability_id,
                proposed_action=raw_output.get("action", "execute"),
                bindings=raw_output.get("bindings", raw_output),
                uncertainty_score=0.0,  # Exact computation has zero neural uncertainty
                evidence={"execution_mode": mode.value, "execution_time_ms": (time.time() - t0) * 1000},
            )
            return proposal

        elif mode == DeploymentMode.REMOTE_CAPABILITY:
            # Remote peer dispatch
            if not self._remote_dispatcher:
                raise MagazineRuntimeError(f"No remote dispatcher configured for capability '{capability_id}'")
            return self._remote_dispatcher(capability_id, work_request)

        elif mode in (DeploymentMode.RESIDENT_ADAPTER, DeploymentMode.PAGED_ADAPTER, DeploymentMode.FIXED_SPECIALIST_EXPORT):
            # Neural inference path
            if not self._neural_generator:
                raise MagazineRuntimeError(f"No neural generator configured for mode {mode}")

            # Switch adapter in magazine manager if available
            switch_ms = 0.0
            if self.magazine_manager and mode != DeploymentMode.FIXED_SPECIALIST_EXPORT:
                if mode == DeploymentMode.PAGED_ADAPTER:
                    # In paged mode, ensure memory budget is constrained to 1 slot
                    self.magazine_manager.residency.max_resident_slots = 1
                switch_ms = self.magazine_manager.switch_adapter(capability_id)

            prompt = context_prompt or str(work_request.payload)
            gen_text = self._neural_generator(capability_id, prompt)

            # Parse proposal JSON
            import json
            try:
                parsed = json.loads(gen_text)
            except Exception:
                # If wrapped or malformed
                parsed = {"action": "unparsed_proposal", "raw": gen_text}

            proposal = CapabilityProposal(
                proposal_id=f"prop-neural-{work_request.work_id}",
                work_id=work_request.work_id,
                producer_identity=f"neural:{self.magazine_manager.foundation_id if self.magazine_manager else 'standalone'}:{capability_id}",
                capability_id=capability_id,
                proposed_action=parsed.get("action", "propose"),
                bindings=parsed.get("bindings", parsed.get("parameters", parsed)),
                uncertainty_score=float(parsed.get("uncertainty", 0.05)),
                evidence={
                    "execution_mode": mode.value,
                    "switch_latency_ms": switch_ms,
                    "generation_time_ms": (time.time() - t0) * 1000,
                },
            )
            return proposal

        else:
            raise MagazineRuntimeError(f"Unsupported deployment mode: {mode}")
