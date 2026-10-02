"""v3.2 Governance Witness Intake Validator.

Enforces the deficit-driven development intake rules for UoW v3.2.
Guarantees that:
    Delta Architecture = 0 unless D(W) > 0
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
import yaml

SCHEMA_VERSION = "uow.v32.witness.v1"

PERMITTED_CATEGORIES = {
    "MISSING_ARCHITECTURAL_PRIMITIVE",
    "BOUNDARY_FAILURE_NEW_CONDITION",
    "SUBSTRATE_REALIZATION_INCOMPATIBILITY",
}

PERMITTED_STATUSES = {
    "INTAKE",
    "REPRODUCED",
    "FALSIFIED",
    "QUALIFIES",
    "CLOSED",
}

PERMITTED_RESULTS = {
    "PENDING",
    "NO_DEFICIT",
    "EXISTING_ARCHITECTURE_SUFFICIENT",
    "PATCH_ONLY",
    "MISSING_ARCHITECTURAL_PRIMITIVE",
    "BOUNDARY_FAILURE_NEW_CONDITION",
    "SUBSTRATE_REALIZATION_INCOMPATIBILITY",
}

HEX_SHA_REGEX = re.compile(r"^[0-9a-fA-F]{40}$")


def validate_witness_dict(data: Dict[str, Any]) -> List[str]:
    """Validate a witness record dictionary against v3.2 governance rules.

    Returns a list of validation error messages. An empty list signifies success.
    """
    errors: List[str] = []

    # 1. Schema version
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(f"Invalid schema_version '{version}'; expected '{SCHEMA_VERSION}'")

    # 2. Witness metadata
    witness = data.get("witness")
    if not isinstance(witness, dict):
        errors.append("Missing or invalid 'witness' block")
    else:
        witness_id = witness.get("id")
        if not witness_id or not isinstance(witness_id, str) or not witness_id.strip():
            errors.append("Missing required 'witness.id'")

    # 3. Baseline commit
    baseline = data.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("Missing or invalid 'baseline' block")
    else:
        release_commit = baseline.get("release_commit")
        dev_commit = baseline.get("development_commit")
        has_valid_sha = False
        if release_commit and isinstance(release_commit, str) and HEX_SHA_REGEX.match(release_commit.strip()):
            has_valid_sha = True
        elif dev_commit and isinstance(dev_commit, str) and HEX_SHA_REGEX.match(dev_commit.strip()):
            has_valid_sha = True

        if not has_valid_sha:
            errors.append(
                "Missing or invalid baseline commit SHA (must provide 40-hex SHA in 'release_commit' or 'development_commit')"
            )

    # 4. Classification
    classification = data.get("classification")
    category = None
    if not isinstance(classification, dict):
        errors.append("Missing or invalid 'classification' block")
    else:
        category = classification.get("category")
        if category not in PERMITTED_CATEGORIES:
            errors.append(
                f"Invalid classification category '{category}'; must be one of {sorted(PERMITTED_CATEGORIES)}"
            )

    # 5. Requirement
    req = data.get("requirement")
    if not isinstance(req, dict):
        errors.append("Missing or invalid 'requirement' block")
    else:
        invariant = req.get("expected_invariant")
        if not invariant or not isinstance(invariant, str) or not invariant.strip():
            errors.append("Missing required 'requirement.expected_invariant'")

    # 6. Observation
    obs = data.get("observation")
    if not isinstance(obs, dict):
        errors.append("Missing or invalid 'observation' block")
    else:
        observed = obs.get("observed_behavior")
        expected = obs.get("expected_behavior")
        if not observed or not isinstance(observed, str) or not observed.strip():
            errors.append("Missing required 'observation.observed_behavior'")
        if not expected or not isinstance(expected, str) or not expected.strip():
            errors.append("Missing required 'observation.expected_behavior'")

    # 7. Reproduction
    repro = data.get("reproduction")
    if not isinstance(repro, dict):
        errors.append("Missing or invalid 'reproduction' block")
    else:
        cmds = repro.get("commands")
        if not isinstance(cmds, list) or len(cmds) == 0:
            errors.append("Missing required reproduction instructions in 'reproduction.commands' (must be non-empty list)")

    # 8. Falsification
    fals = data.get("falsification")
    if not isinstance(fals, dict):
        errors.append("Missing or invalid 'falsification' block")
    else:
        null_h = fals.get("null_hypothesis")
        if not null_h or not isinstance(null_h, str) or not null_h.strip():
            errors.append("Missing required 'falsification.null_hypothesis'")
        neg_ctrl = fals.get("negative_controls")
        if not isinstance(neg_ctrl, list):
            errors.append("Missing 'falsification.negative_controls' (must be a list)")
        acc = fals.get("acceptance_criteria")
        if not isinstance(acc, list) or len(acc) == 0:
            errors.append("Missing 'falsification.acceptance_criteria' (must be non-empty list)")
        rej = fals.get("rejection_criteria")
        if not isinstance(rej, list) or len(rej) == 0:
            errors.append("Missing 'falsification.rejection_criteria' (must be non-empty list)")

    # 9. Disposition
    disp = data.get("disposition")
    status = None
    result = None
    if not isinstance(disp, dict):
        errors.append("Missing or invalid 'disposition' block")
    else:
        status = disp.get("status")
        result = disp.get("result")
        if status not in PERMITTED_STATUSES:
            errors.append(f"Invalid disposition.status '{status}'; must be one of {sorted(PERMITTED_STATUSES)}")
        if result not in PERMITTED_RESULTS:
            errors.append(f"Invalid disposition.result '{result}'; must be one of {sorted(PERMITTED_RESULTS)}")

    # 10. Change Authorization
    auth = data.get("change_authorization")
    change_allowed = False
    if not isinstance(auth, dict):
        errors.append("Missing or invalid 'change_authorization' block")
    else:
        change_allowed = bool(auth.get("architectural_change_allowed", False))

    # 11. Relational Invariants
    # Invariant A: architectural_change_allowed can ONLY be True when status == QUALIFIES
    if change_allowed and status != "QUALIFIES":
        errors.append(
            f"Violation: 'architectural_change_allowed' cannot be True when status is '{status}' (only permitted on 'QUALIFIES')"
        )

    # Invariant B: status == QUALIFIES requires a permitted deficit category in result
    if status == "QUALIFIES":
        if result not in PERMITTED_CATEGORIES:
            errors.append(
                f"Violation: status 'QUALIFIES' requires disposition.result in {sorted(PERMITTED_CATEGORIES)}, got '{result}'"
            )
        if category and result != category:
            errors.append(
                f"Violation: disposition.result ('{result}') does not match classification.category ('{category}')"
            )

    # Invariant C: Non-deficit results cannot authorize architectural changes
    if result in {"NO_DEFICIT", "EXISTING_ARCHITECTURE_SUFFICIENT", "PATCH_ONLY"}:
        if change_allowed:
            errors.append(
                f"Violation: 'architectural_change_allowed' cannot be True when result is '{result}'"
            )
        if status == "QUALIFIES":
            errors.append(
                f"Violation: status cannot be 'QUALIFIES' when result is '{result}'"
            )

    return errors


def validate_witness_file(path: Path | str) -> List[str]:
    """Validate a witness YAML file from disk."""
    p = Path(path)
    if not p.exists():
        return [f"File not found: {p}"]

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        return [f"Failed to parse YAML from {p}: {exc}"]

    if not isinstance(data, dict):
        return [f"Root structure in {p} must be a mapping, got {type(data).__name__}"]

    return validate_witness_dict(data)


def validate_all_witnesses(witnesses_dir: Path | str | None = None) -> Tuple[int, List[str]]:
    """Scan and validate all active witness YAML files in the witness directory.

    Returns (validated_count, list_of_error_strings).
    """
    if witnesses_dir is None:
        repo_root = Path(__file__).resolve().parent.parent
        witnesses_dir = repo_root / "governance" / "v32" / "witnesses"
    else:
        witnesses_dir = Path(witnesses_dir)

    if not witnesses_dir.exists():
        return 0, [f"Witnesses directory does not exist: {witnesses_dir}"]

    files = sorted(
        [
            f
            for f in witnesses_dir.glob("*.y*ml")
            if not f.name.startswith(".") and "template" not in f.name.lower()
        ]
    )

    all_errors: List[str] = []
    count = 0
    for f in files:
        count += 1
        file_errors = validate_witness_file(f)
        for err in file_errors:
            all_errors.append(f"[{f.name}] {err}")

    return count, all_errors


def main() -> int:
    """CLI entrypoint for witness intake validation."""
    parser = argparse.ArgumentParser(description="Validate UoW v3.2 Deficit Witness Records")
    parser.add_argument("--validate-all", action="store_true", help="Validate all witness records in governance/v32/witnesses/")
    parser.add_argument("--file", type=str, help="Validate a specific witness YAML file")
    args = parser.parse_args()

    if args.file:
        errors = validate_witness_file(args.file)
        if errors:
            print(f"FAILED: {args.file} has {len(errors)} error(s):", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        print(f"PASSED: {args.file} is a valid v3.2 witness record.")
        return 0

    count, errors = validate_all_witnesses()
    if errors:
        print(f"FAILED: Found {len(errors)} error(s) across {count} witness record(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"PASSED: Validated {count} v3.2 witness record(s) with 0 errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
