"""Qualified semantic mediation surface.

This subpackage is intentionally not promoted into the frozen top-level uow
compatibility facade. Import from uow.semantic explicitly while qualification
is in progress.
"""

from .application import (
    PreparedSemanticUoW,
    SemanticApplicationAdapter,
    SemanticStateDriftError,
)
from .clarification import (
    ClarificationContext,
    ContradictoryContinuationError,
    StaleClarificationError,
)
from .compiler import (
    PurgeUoWCompiler,
    SemanticCompilerRegistry,
    SemanticUoWCompiler,
    TransferUoWCompiler,
    derive_semantic_uow_id,
)
from .context import SemanticContextProjector
from .egress import GovernedEgressEngine, GovernedEgressMessage
from .frontier import DeterministicSemanticResolver, SemanticFrontierBuilder
from .handoff import SemanticHandoff
from .harness import SemanticHarness
from .projection import (
    ProjectedSemanticIntent,
    RecipientClass,
    RecipientProfile,
    SemanticRecipientProjector,
)
from .rendering import (
    ConfigurableRenderer,
    DeterministicEgressFormatter,
    DeterministicTemplateRenderer,
    SemanticRenderer,
)
from .roundtrip import SemanticRoundTripResult, SemanticRoundTripVerifier
from .schema import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    IngressContext,
    IntentEnvelope,
    MinimalSemanticContext,
    SemanticAlternative,
    SemanticBinding,
    SemanticClosureCertificate,
    SemanticDisposition,
    SemanticFrontierResult,
    SemanticInvariantError,
    SemanticRequirement,
    SemanticResult,
    SemanticTranslationRequest,
)
from .translator import NullSemanticTranslator, SemanticTranslator
from .validation import (
    BindingValidationResult,
    DefaultSemanticAdmissibilityValidator,
    SemanticBindingValidator,
    ValidationVerdict,
)

__all__ = [
    "BindingOrigin",
    "BindingValidationResult",
    "CandidateSemanticBindings",
    "ClarificationContext",
    "ConfigurableRenderer",
    "ContradictoryContinuationError",
    "DefaultSemanticAdmissibilityValidator",
    "DeterministicEgressFormatter",
    "DeterministicSemanticResolver",
    "DeterministicTemplateRenderer",
    "ExternalSignal",
    "GovernedEgressEngine",
    "GovernedEgressMessage",
    "IngressContext",
    "IntentEnvelope",
    "MinimalSemanticContext",
    "NullSemanticTranslator",
    "PreparedSemanticUoW",
    "ProjectedSemanticIntent",
    "PurgeUoWCompiler",
    "RecipientClass",
    "RecipientProfile",
    "SemanticAlternative",
    "SemanticApplicationAdapter",
    "SemanticBinding",
    "SemanticBindingValidator",
    "SemanticClosureCertificate",
    "SemanticCompilerRegistry",
    "SemanticContextProjector",
    "SemanticDisposition",
    "SemanticFrontierBuilder",
    "SemanticFrontierResult",
    "SemanticHandoff",
    "SemanticHarness",
    "SemanticInvariantError",
    "SemanticRecipientProjector",
    "SemanticRenderer",
    "SemanticRequirement",
    "SemanticResult",
    "SemanticRoundTripResult",
    "SemanticRoundTripVerifier",
    "SemanticStateDriftError",
    "SemanticTranslationRequest",
    "SemanticTranslator",
    "SemanticUoWCompiler",
    "StaleClarificationError",
    "TransferUoWCompiler",
    "ValidationVerdict",
    "derive_semantic_uow_id",
]
