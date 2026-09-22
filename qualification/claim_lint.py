"""Qualification claim-registry lint.

The lint is intentionally conservative. It validates the declarative evidence
requirements themselves and provides one CI entry point for future claims.
"""
from __future__ import annotations

from qualification.claim_registry import CLAIMS
from qualification.evidence import EvidenceLevel


def lint_claim_registry() -> list[str]:
    errors: list[str] = []
    ids = list(CLAIMS)

    if len(ids) != len(set(ids)):
        errors.append("duplicate claim IDs")

    for key, spec in CLAIMS.items():
        if key != spec.claim_id:
            errors.append(f"{key}: registry key differs from claim_id {spec.claim_id}")
        if not spec.statement.strip():
            errors.append(f"{key}: empty claim statement")
        if spec.required_level is EvidenceLevel.PHYSICAL and not spec.required_components:
            errors.append(f"{key}: physical claim declares no required actual components")
        if spec.measurement_source in {"proxy", "synthetic_proxy", "estimated_proxy"}:
            errors.append(f"{key}: proxy measurement cannot be normative claim evidence")
        if spec.requires_negative_control and spec.required_level is EvidenceLevel.SIMULATED:
            errors.append(f"{key}: negative-control enforcement claim is only simulated")

    return errors


def main() -> int:
    errors = lint_claim_registry()
    if errors:
        for error in errors:
            print(f"CLAIM-LINT FAIL: {error}")
        return 1
    print(f"CLAIM-LINT PASS: {len(CLAIMS)} registered qualification claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
