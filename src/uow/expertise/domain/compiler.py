"""Domain Context Compiler (WP04).

Compiles authoritative domain schemas and relevant entity subsets into structured
prompt context for compact neural interpreters.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from uow.protocol.v1 import canonical_json
from .models import DomainPackage


class DomainContextCompiler:
    """Compiles domain knowledge into compact, unambiguous interpreter context."""

    def __init__(self, domain_package: DomainPackage) -> None:
        self.domain = domain_package

    def compile_prompt(
        self,
        grammar: str,
        work_payload: Dict[str, Any],
        pre_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Compile a domain-grounded prompt matching the exact format used during training."""
        domain_name = self.domain.name.upper()
        header = (
            f"You are the deterministic UoW Grounded {grammar.capitalize()} Proposer "
            f"for the {domain_name} domain (uow.{grammar}.v1).\n"
            f"Domain ID: {self.domain.domain_id} (version {self.domain.version})\n\n"
        )

        # Entity catalog excerpt
        entities_summary = [
            f"- {eid} ({edef.entity_type}, allowed_states: {', '.join(edef.allowed_states)})"
            for eid, edef in list(self.domain.entities.items())[:10]
        ]

        # Action catalog excerpt
        actions_summary = [
            f"- {act.action_name}: requires [{', '.join(act.required_parameters)}]"
            for act in list(self.domain.actions.values())[:8]
        ]

        context_block = (
            "AUTHORITATIVE DOMAIN SPECIFICATION:\n"
            "Entities:\n" + "\n".join(entities_summary) + "\n\n"
            "Valid Operations:\n" + "\n".join(actions_summary) + "\n\n"
        )

        input_block = (
            "CURRENT WORK INGRESS:\n"
            f"Payload: {json.dumps(work_payload, sort_keys=True)}\n"
        )
        if pre_state:
            input_block += f"Pre-State: {json.dumps(pre_state, sort_keys=True)}\n"

        instruction = (
            "\nTASK: Emit exactly one valid JSON object conforming to the UoW proposal contract. "
            "Never fabricate entity identifiers outside the authoritative domain register."
        )

        return header + context_block + input_block + instruction
