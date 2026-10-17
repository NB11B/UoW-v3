"""Deterministic-First Execution Planner and Composition Orchestrator (WP06).

Enforces the deterministic-first policy:
1. Exact deterministic computation if available.
2. Grounded neural specialist if qualified.
3. Independent UoW certification.
4. Explanatory audit trail detailing selection rationale, compute cost, and alternatives.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.uow.capabilities import (
    CapabilityLifecycleState,
    CapabilityRecord,
    UniversalCapabilityRegistry,
)
from src.uow.expertise.domain import (
    DomainContextCompiler,
    DomainGroundingValidator,
    DomainPackage,
    GroundingValidationResult,
)
from src.uow.magazine.deployment import DeploymentMode, MagazineDeploymentEngine
from src.uow.protocol.v1 import (
    CapabilityKind,
    CapabilityProposal,
    CommitDisposition,
    CommitRecord,
    QualificationStatus,
    WorkCertificate,
    WorkRequest,
)


@dataclass(frozen=True)
class ExecutionAuditStep:
    step_name: str
    decision: str
    rationale: str
    latency_ms: float
    cost_tokens: int = 0
    artifacts: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlanResult:
    work_id: str
    success: bool
    final_disposition: CommitDisposition
    proposal: Optional[CapabilityProposal]
    certificate: Optional[WorkCertificate]
    audit_trail: List[ExecutionAuditStep] = field(default_factory=list)
    rejection_reason: Optional[str] = None

    @property
    def total_latency_ms(self) -> float:
        return sum(s.latency_ms for s in self.audit_trail)

    def explain(self) -> str:
        """Produce human-readable explanation of routing and execution decisions."""
        lines = [f"=== Execution Audit Trail for Work {self.work_id} ==="]
        lines.append(f"Disposition: {self.final_disposition.value} | Success: {self.success}")
        if self.rejection_reason:
            lines.append(f"Rejection Reason: {self.rejection_reason}")
        lines.append("Steps:")
        for idx, s in enumerate(self.audit_trail, 1):
            lines.append(
                f"  [{idx}] {s.step_name}: {s.decision} ({s.latency_ms:.2f}ms) - {s.rationale}"
            )
        return "\n".join(lines)


class ExecutionPlanner:
    """Orchestrates deterministic-first execution, neural interpretation, and authority submission."""

    def __init__(
        self,
        registry: UniversalCapabilityRegistry,
        deployment_engine: MagazineDeploymentEngine,
        domain_packages: Optional[Dict[str, DomainPackage]] = None,
        authority_certifier: Optional[Callable[[CapabilityProposal, str], WorkCertificate]] = None,
    ) -> None:
        self.registry = registry
        self.deployment_engine = deployment_engine
        self.domain_packages = domain_packages or {}
        self._certifier = authority_certifier

    def register_domain(self, domain_package: DomainPackage) -> None:
        self.domain_packages[domain_package.domain_id] = domain_package

    def execute_work(
        self,
        work_request: WorkRequest,
        pre_state_hash: str,
    ) -> ExecutionPlanResult:
        """Execute a work request following the deterministic-first policy."""
        audit: List[ExecutionAuditStep] = []
        cap_id = work_request.requested_capability
        t0 = time.time()

        # Step 1: Capability Resolution
        rec = self.registry.get(cap_id)
        if not rec:
            audit.append(
                ExecutionAuditStep(
                    step_name="Capability Resolution",
                    decision="REFUSED",
                    rationale=f"Capability '{cap_id}' is not registered in capability registry.",
                    latency_ms=(time.time() - t0) * 1000,
                )
            )
            return ExecutionPlanResult(
                work_id=work_request.work_id,
                success=False,
                final_disposition=CommitDisposition.REJECTED,
                proposal=None,
                certificate=None,
                audit_trail=audit,
                rejection_reason=f"Unknown capability: {cap_id}",
            )

        # Step 2: Route Selection (Deterministic vs Neural)
        # Check if an exact deterministic substitute is available
        det_substitute_id = f"det.{cap_id}"
        det_record = self.registry.get(det_substitute_id)
        selected_cap_id = cap_id
        is_deterministic = False

        if rec.kind == CapabilityKind.DETERMINISTIC:
            is_deterministic = True
            audit.append(
                ExecutionAuditStep(
                    step_name="Route Selection",
                    decision="DETERMINISTIC_DIRECT",
                    rationale="Requested capability is intrinsically deterministic; zero neural compute needed.",
                    latency_ms=(time.time() - t0) * 1000,
                )
            )
        elif det_record and det_record.is_invokable:
            is_deterministic = True
            selected_cap_id = det_substitute_id
            audit.append(
                ExecutionAuditStep(
                    step_name="Route Selection",
                    decision="DETERMINISTIC_SUBSTITUTE",
                    rationale=f"Exact deterministic provider '{det_substitute_id}' preferred over neural interpretation.",
                    latency_ms=(time.time() - t0) * 1000,
                )
            )
        else:
            audit.append(
                ExecutionAuditStep(
                    step_name="Route Selection",
                    decision="NEURAL_SPECIALIST",
                    rationale=f"No exact deterministic provider available; invoking learned specialist '{cap_id}'.",
                    latency_ms=(time.time() - t0) * 1000,
                )
            )

        # Step 3: Domain Context Compilation (if neural)
        context_prompt: Optional[str] = None
        domain_pkg: Optional[DomainPackage] = None
        for dep in rec.descriptor.dependencies:
            if dep in self.domain_packages:
                domain_pkg = self.domain_packages[dep]
                break

        if not is_deterministic and domain_pkg:
            t_comp = time.time()
            compiler = DomainContextCompiler(domain_pkg)
            grammar = rec.descriptor.implementation_metadata.get("grammar", "operational")
            context_prompt = compiler.compile_prompt(grammar, work_request.payload)
            audit.append(
                ExecutionAuditStep(
                    step_name="Context Compilation",
                    decision="CONTEXT_INJECTED",
                    rationale=f"Authoritative ontology from '{domain_pkg.domain_id}' injected into prompt.",
                    latency_ms=(time.time() - t_comp) * 1000,
                )
            )

        # Step 4: Proposal Generation
        t_gen = time.time()
        try:
            proposal = self.deployment_engine.execute_capability(
                selected_cap_id,
                work_request,
                context_prompt=context_prompt,
            )
        except Exception as e:
            audit.append(
                ExecutionAuditStep(
                    step_name="Capability Execution",
                    decision="EXECUTION_ERROR",
                    rationale=f"Capability execution failed with exception: {e}",
                    latency_ms=(time.time() - t_gen) * 1000,
                )
            )
            return ExecutionPlanResult(
                work_id=work_request.work_id,
                success=False,
                final_disposition=CommitDisposition.REJECTED,
                proposal=None,
                certificate=None,
                audit_trail=audit,
                rejection_reason=str(e),
            )

        # Step 5: Proposal Invariant Check
        if not proposal.validate_boundary():
            audit.append(
                ExecutionAuditStep(
                    step_name="Authority Boundary Check",
                    decision="INTERCEPTED_ROGUE_PROPOSAL",
                    rationale="Proposal attempted to smuggle authority assertions into unprivileged proposal.",
                    latency_ms=0.1,
                )
            )
            return ExecutionPlanResult(
                work_id=work_request.work_id,
                success=False,
                final_disposition=CommitDisposition.QUARANTINED,
                proposal=proposal,
                certificate=None,
                audit_trail=audit,
                rejection_reason="Proposal violated authority boundary invariant.",
            )

        # Step 6: Domain Grounding Validation (if domain package exists)
        if domain_pkg:
            t_ground = time.time()
            validator = DomainGroundingValidator(domain_pkg)
            g_res = validator.validate(proposal.proposed_action, proposal.bindings)
            if not g_res.is_valid:
                reasons = g_res.grounding_violations + g_res.safety_violations
                audit.append(
                    ExecutionAuditStep(
                        step_name="Domain Grounding",
                        decision="GROUNDING_FAILED",
                        rationale=f"Grounding violations: {'; '.join(reasons)}",
                        latency_ms=(time.time() - t_ground) * 1000,
                    )
                )
                return ExecutionPlanResult(
                    work_id=work_request.work_id,
                    success=False,
                    final_disposition=CommitDisposition.REJECTED,
                    proposal=proposal,
                    certificate=None,
                    audit_trail=audit,
                    rejection_reason=f"Domain grounding failed: {'; '.join(reasons)}",
                )
            else:
                audit.append(
                    ExecutionAuditStep(
                        step_name="Domain Grounding",
                        decision="GROUNDING_VERIFIED",
                        rationale="All action parameters and entity identifiers grounded in authoritative register.",
                        latency_ms=(time.time() - t_ground) * 1000,
                    )
                )

        # Step 7: Independent UoW Authority Certification
        if self._certifier:
            t_cert = time.time()
            cert = self._certifier(proposal, pre_state_hash)
            audit.append(
                ExecutionAuditStep(
                    step_name="UoW Certification",
                    decision="CERTIFIED" if cert.is_valid else "DENIED",
                    rationale=cert.rejection_reason or "Proposal satisfied route guards and pre-state invariants.",
                    latency_ms=(time.time() - t_cert) * 1000,
                )
            )
            disposition = CommitDisposition.COMMITTED if cert.is_valid else CommitDisposition.REJECTED
            return ExecutionPlanResult(
                work_id=work_request.work_id,
                success=cert.is_valid,
                final_disposition=disposition,
                proposal=proposal,
                certificate=cert,
                audit_trail=audit,
                rejection_reason=cert.rejection_reason,
            )

        # If no explicit certifier attached, return uncertified proposal
        return ExecutionPlanResult(
            work_id=work_request.work_id,
            success=True,
            final_disposition=CommitDisposition.COMMITTED,
            proposal=proposal,
            certificate=None,
            audit_trail=audit,
        )
