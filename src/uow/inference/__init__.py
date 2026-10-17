"""uow.inference package: Model-Independent Inference Gateway."""
from uow.inference.request_context import (
    InferenceRequest,
    InferenceResponse,
    TypedProposal,
    CapabilityTarget,
    StateReference,
)
from uow.inference.model_backend import (
    ModelBackend,
    PyTorchPeftBackend,
    MockModelBackend,
)
from uow.inference.output_validation import (
    ProposalOutputValidator,
    OutputValidationError,
)
from uow.inference.routing import (
    CapabilityRouter,
    RoutingResolutionError,
)
from uow.inference.gateway import InferenceGateway
from uow.inference.authority_bridge import AuthorityBridge, AuthorityEvaluation

__all__ = [
    "InferenceRequest",
    "InferenceResponse",
    "TypedProposal",
    "CapabilityTarget",
    "StateReference",
    "ModelBackend",
    "PyTorchPeftBackend",
    "MockModelBackend",
    "ProposalOutputValidator",
    "OutputValidationError",
    "CapabilityRouter",
    "RoutingResolutionError",
    "InferenceGateway",
    "AuthorityBridge",
    "AuthorityEvaluation",
]
