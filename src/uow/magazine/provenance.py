"""Cryptographic Provenance and Audit Trails for Magazine Invocations."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
import time


@dataclass(frozen=True)
class ProposalProvenance:
    """Immutable audit metadata attached to every neural proposal emitted by the magazine."""
    request_id: str
    foundation_model: str
    foundation_revision: str
    adapter_id: str
    adapter_sha256: str
    domain: str
    grammar: str
    target_schema: str
    inference_device: str
    switch_latency_ms: float
    inference_latency_ms: float
    timestamp_utc: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["timestamp_utc"] == 0.0:
            d["timestamp_utc"] = time.time()
        return d
