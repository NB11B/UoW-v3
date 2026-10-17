"""Inference Gateway: Subsystem S4 Reference Implementation (uow.inference.v1)."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from uow.inference.request_context import (
    InferenceRequest,
    InferenceResponse,
    TypedProposal,
)
from uow.inference.routing import CapabilityRouter, RoutingResolutionError
from uow.inference.output_validation import ProposalOutputValidator
from uow.inference.model_backend import ModelBackend
from uow.magazine.manager import MagazineManager


class InferenceGateway:
    """Entry point for model-independent UoW inference transactions."""

    def __init__(
        self,
        magazine_manager: MagazineManager,
        model_backend: ModelBackend,
        router: Optional[CapabilityRouter] = None,
    ) -> None:
        self.magazine_manager = magazine_manager
        self.backend = model_backend
        self.router = router or CapabilityRouter()

    def process_request(self, request: InferenceRequest) -> InferenceResponse:
        """Processes an incoming work request and produces a typed proposal."""
        req_id = request.request_id or f"req_{int(time.time() * 1000)}"

        # 1. Route to domain and grammar
        try:
            domain, grammar = self.router.route_request(request)
        except RoutingResolutionError as r_err:
            return InferenceResponse(
                protocol=request.protocol,
                request_id=req_id,
                status="CLARIFICATION_REQUIRED",
                error_message=str(r_err),
            )

        # 2. Resolve verified adapter from registry
        adapter_id = self.magazine_manager.registry.resolve_capability(domain, grammar)
        if not adapter_id:
            return InferenceResponse(
                protocol=request.protocol,
                request_id=req_id,
                status="REJECTED",
                error_message=f"No verified resident adapter available for capability '{domain}.{grammar}'",
            )

        # 3. Format input prompt
        prompt = request.prompt_text
        if not prompt:
            signal = request.input_data.get("signal", "")
            prompt = (
                f"<|im_start|>system\nYou are the deterministic UoW Proposal Parser for {domain.upper()} ({grammar}).<|im_end|>\n"
                f"<|im_start|>user\n{signal}<|im_end|>\n<|im_start|>assistant\n"
            )

        # 4. Execute inference under serialized transaction queue with rollback guard
        try:
            raw_output, provenance = self.magazine_manager.execute_request_transaction(
                request_id=req_id,
                adapter_id=adapter_id,
                inference_fn=lambda: self.backend.generate(prompt),
            )
        except Exception as e:
            return InferenceResponse(
                protocol=request.protocol,
                request_id=req_id,
                status="ERROR",
                error_message=f"Inference execution failed: {e}",
            )

        # 5. Strictly validate output schema against expected grammar
        is_valid, parsed_dict, val_err = ProposalOutputValidator.validate_proposal(raw_output, grammar)
        if not is_valid or parsed_dict is None:
            return InferenceResponse(
                protocol=request.protocol,
                request_id=req_id,
                status="REJECTED",
                error_message=f"Model output violated grammar schema: {val_err}",
                provenance=provenance.to_dict(),
            )

        # 6. Construct typed advisory proposal
        typed_prop = TypedProposal(
            proposal_type="PROPOSAL",
            grammar=grammar,
            payload=parsed_dict,
            confidence_status="UNVERIFIED",
            requires_certification=True,
        )

        return InferenceResponse(
            protocol=request.protocol,
            request_id=req_id,
            status="OK",
            result=typed_prop,
            provenance=provenance.to_dict(),
        )
