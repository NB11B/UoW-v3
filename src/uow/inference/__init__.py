"""uow.inference package: Model-Independent Inference Gateway."""
from src.uow.inference.request_context import (
    InferenceRequest,
    InferenceResponse,
    TypedProposal,
    CapabilityTarget,
    StateReference,
)
from src.uow.inference.model_backend import (
    ModelBackend,
    PyTorchPeftBackend,
    MockModelBackend,
)
from src.uow.inference.output_validation import (
    ProposalOutputValidator,
    OutputValidationError,
)
from src.uow.inference.routing import (
    CapabilityRouter,
    RoutingResolutionError,
)
from src.uow.inference.gateway import InferenceGateway
from src.uow.inference.authority_bridge import AuthorityBridge, AuthorityEvaluation

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
