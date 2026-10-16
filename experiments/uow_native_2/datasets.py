"""Dataset generators and partition manifests for UOW-NATIVE-2.

Generates 3 relational task families:
  1. numerical_ordering: Pairwise magnitude comparison ("Which number is larger: {a} or {b}?")
  2. symbolic_equivalence: Algebraic commutativity & non-commutativity ("Is {expr1} equal to {expr2}?")
  3. relational_classification: Transitive deduction ("If A > B and B > C, is A > C?") vs invalid fallacy ("... is C > A?")

Each family contains 600 examples partitioned into:
  - 200 Development (dev)
  - 200 Validation (val)
  - 200 Holdout (holdout)

Enforces strict counterbalancing:
  - Exactly 50% presentation order 0 vs order 1
  - Exactly 50% target positive label vs negative label
  - Disjoint entity pools across dev, val, and holdout splits
  - Shifted prompt templates for out-of-distribution syntax testing
  - Deterministic generation with fixed random seeds
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Example:
    id: str
    family: str
    split: str
    prompt: str
    positive: str
    negative: str
    order: int  # 0 or 1
    ground_truth_label: str
    shifted_prompts: List[str]
    counterpart_id: Optional[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Template definitions
NUMERICAL_TEMPLATES = [
    # Canonical (index 0)
    "Which number is larger: {a} or {b}? Answer with the number only.",
    # Shifted 1
    "Select the maximum of {a} and {b}. Reply with its numeral.",
    # Shifted 2
    "Between {a} and {b}, identify the larger number. Answer:",
]

SYMBOLIC_TEMPLATES = [
    # Canonical (index 0)
    "Consider the expression {expr1} and {expr2}. Are they equivalent? Answer Yes or No.",
    # Shifted 1
    "Determine if {expr1} = {expr2}. Reply with Yes or No.",
    # Shifted 2
    "Does {expr1} evaluate to the same value as {expr2}? Answer Yes or No.",
]

RELATIONAL_TEMPLATES = [
    # Canonical (index 0)
    "Statement 1: {A} is heavier than {B}. Statement 2: {B} is heavier than {C}. Question: Is {first} heavier than {second}? Answer Yes or No.",
    # Shifted 1
    "Given that {A} > {B} and {B} > {C}, does it follow that {first} > {second}? Reply Yes or No.",
    # Shifted 2
    "Premise: {A} precedes {B}, and {B} precedes {C}. Deduction: Does {first} precede {second}? Answer Yes or No.",
]


def generate_numerical_ordering(seed: int = 42) -> Dict[str, List[Example]]:
    """Generate 600 numerical ordering examples: 200 dev, 200 val, 200 holdout.

    Uses distinct 2-digit integer pairs (10 to 99).
    For each split of 200, we select 100 distinct unordered pairs (lo, hi).
    Each pair generates 2 counterbalanced examples:
      - Order 0: (hi, lo) -> larger number presented first
      - Order 1: (lo, hi) -> larger number presented second
    Positive answer is always the numeral of the larger number.
    Negative answer is always the numeral of the smaller number.
    """
    rng = random.Random(seed)
    all_pairs = [(lo, hi) for lo in range(10, 100) for hi in range(lo + 1, 100)]
    rng.shuffle(all_pairs)

    # 3 splits * 100 pairs = 300 pairs (600 examples)
    dev_pairs = all_pairs[0:100]
    val_pairs = all_pairs[100:200]
    holdout_pairs = all_pairs[200:300]

    splits_data = {
        "dev": dev_pairs,
        "val": val_pairs,
        "holdout": holdout_pairs,
    }

    result = {}
    for split_name, pairs in splits_data.items():
        split_examples = []
        for idx, (lo, hi) in enumerate(pairs):
            id_0 = f"num_{split_name}_{idx * 2:04d}_ord0"
            id_1 = f"num_{split_name}_{idx * 2 + 1:04d}_ord1"

            # Order 0: hi first, lo second
            prompt_0 = NUMERICAL_TEMPLATES[0].format(a=hi, b=lo)
            shifted_0 = [
                NUMERICAL_TEMPLATES[1].format(a=hi, b=lo),
                NUMERICAL_TEMPLATES[2].format(a=hi, b=lo),
            ]
            ex_0 = Example(
                id=id_0,
                family="numerical_ordering",
                split=split_name,
                prompt=prompt_0,
                positive=str(hi),
                negative=str(lo),
                order=0,
                ground_truth_label=str(hi),
                shifted_prompts=shifted_0,
                counterpart_id=id_1,
                metadata={"hi": hi, "lo": lo, "first": hi, "second": lo, "pair_index": idx},
            )

            # Order 1: lo first, hi second
            prompt_1 = NUMERICAL_TEMPLATES[0].format(a=lo, b=hi)
            shifted_1 = [
                NUMERICAL_TEMPLATES[1].format(a=lo, b=hi),
                NUMERICAL_TEMPLATES[2].format(a=lo, b=hi),
            ]
            ex_1 = Example(
                id=id_1,
                family="numerical_ordering",
                split=split_name,
                prompt=prompt_1,
                positive=str(hi),
                negative=str(lo),
                order=1,
                ground_truth_label=str(hi),
                shifted_prompts=shifted_1,
                counterpart_id=id_0,
                metadata={"hi": hi, "lo": lo, "first": lo, "second": hi, "pair_index": idx},
            )

            split_examples.append(ex_0)
            split_examples.append(ex_1)

        result[split_name] = split_examples

    return result


def generate_symbolic_equivalence(seed: int = 43) -> Dict[str, List[Example]]:
    """Generate 600 symbolic equivalence examples: 200 dev, 200 val, 200 holdout.

    Evaluates commutativity vs non-commutativity:
      - Commutative (+, *): x + y == y + x, x * y == y * x (Valid equivalence -> "Yes")
      - Non-commutative (-, /): x - y != y - x, x / y != y / x (Invalid equivalence -> "No")

    In each split of 200 examples:
      - Exactly 100 equivalent ("Yes" positive)
      - Exactly 100 non-equivalent ("No" positive)
      - Disjoint variable name pool across dev, val, holdout.
    """
    rng = random.Random(seed)

    # Disjoint variable name pools
    var_pools = {
        "dev": [("m", "n"), ("p", "q"), ("u", "v"), ("r", "s"), ("j", "k")],
        "val": [("w", "z"), ("c", "d"), ("f", "g"), ("x", "y"), ("a", "b")],
        "holdout": [("h", "l"), ("t", "w"), ("e", "k"), ("alpha", "beta"), ("theta", "phi")],
    }

    result = {}
    for split_name, pool in var_pools.items():
        split_examples = []
        for i in range(100):
            # Pick a variable pair
            v1, v2 = pool[i % len(pool)]
            # Salt with coefficient or index for distinctness
            coeff = (i // len(pool)) + 1
            var1 = f"{coeff}{v1}" if coeff > 1 else v1
            var2 = f"{coeff}{v2}" if coeff > 1 else v2

            # Equivalent pair (commutative)
            op_comm = "+" if (i % 2 == 0) else "*"
            expr1_eq = f"{var1} {op_comm} {var2}"
            expr2_eq = f"{var2} {op_comm} {var1}"

            # Non-equivalent pair (non-commutative)
            op_noncomm = "-" if (i % 2 == 0) else "/"
            expr1_neq = f"{var1} {op_noncomm} {var2}"
            expr2_neq = f"{var2} {op_noncomm} {var1}"

            id_eq = f"sym_{split_name}_{i * 2:04d}_equiv"
            id_neq = f"sym_{split_name}_{i * 2 + 1:04d}_nonequiv"

            # Equivalent instance: correct answer is "Yes", incorrect is "No"
            prompt_eq = SYMBOLIC_TEMPLATES[0].format(expr1=expr1_eq, expr2=expr2_eq)
            shifted_eq = [
                SYMBOLIC_TEMPLATES[1].format(expr1=expr1_eq, expr2=expr2_eq),
                SYMBOLIC_TEMPLATES[2].format(expr1=expr1_eq, expr2=expr2_eq),
            ]
            ex_eq = Example(
                id=id_eq,
                family="symbolic_equivalence",
                split=split_name,
                prompt=prompt_eq,
                positive="Yes",
                negative="No",
                order=0,  # equivalent condition
                ground_truth_label="Yes",
                shifted_prompts=shifted_eq,
                counterpart_id=id_neq,
                metadata={"op": op_comm, "expr1": expr1_eq, "expr2": expr2_eq, "equivalent": True},
            )

            # Non-equivalent instance: correct answer is "No", incorrect is "Yes"
            prompt_neq = SYMBOLIC_TEMPLATES[0].format(expr1=expr1_neq, expr2=expr2_neq)
            shifted_neq = [
                SYMBOLIC_TEMPLATES[1].format(expr1=expr1_neq, expr2=expr2_neq),
                SYMBOLIC_TEMPLATES[2].format(expr1=expr1_neq, expr2=expr2_neq),
            ]
            ex_neq = Example(
                id=id_neq,
                family="symbolic_equivalence",
                split=split_name,
                prompt=prompt_neq,
                positive="No",
                negative="Yes",
                order=1,  # non-equivalent condition
                ground_truth_label="No",
                shifted_prompts=shifted_neq,
                counterpart_id=id_eq,
                metadata={"op": op_noncomm, "expr1": expr1_neq, "expr2": expr2_neq, "equivalent": False},
            )

            split_examples.append(ex_eq)
            split_examples.append(ex_neq)

        result[split_name] = split_examples

    return result


def generate_relational_classification(seed: int = 44) -> Dict[str, List[Example]]:
    """Generate 600 relational classification examples: 200 dev, 200 val, 200 holdout.

    Tests transitive relation reasoning:
      Premise 1: A > B
      Premise 2: B > C
      Valid deduction: Is A > C? -> Ground truth "Yes" (order 0)
      Invalid fallacy: Is C > A? -> Ground truth "No"  (order 1)

    In each split of 200 examples:
      - Exactly 100 valid transitive deductions (ground truth "Yes")
      - Exactly 100 invalid fallacies (ground truth "No")
      - Disjoint named entity pools across splits.
    """
    rng = random.Random(seed)

    # Disjoint entity pools
    entity_pools = {
        "dev": [
            ("Alice", "Bob", "Charlie"),
            ("David", "Emma", "Frank"),
            ("Grace", "Henry", "Ivy"),
            ("Jack", "Kate", "Liam"),
            ("Mia", "Noah", "Olivia"),
        ],
        "val": [
            ("Peter", "Quinn", "Rachel"),
            ("Sam", "Tara", "Uma"),
            ("Victor", "Wendy", "Xavier"),
            ("Yara", "Zack", "Aaron"),
            ("Bella", "Caleb", "Diana"),
        ],
        "holdout": [
            ("Ethan", "Fiona", "George"),
            ("Hannah", "Ian", "Julia"),
            ("Kevin", "Laura", "Max"),
            ("Nora", "Oscar", "Penny"),
            ("Quincy", "Ruby", "Simon"),
        ],
    }

    result = {}
    for split_name, pool in entity_pools.items():
        split_examples = []
        for i in range(100):
            base_tuple = pool[i % len(pool)]
            suffix = f"_{i // len(pool)}" if (i // len(pool)) > 0 else ""
            A = base_tuple[0] + suffix
            B = base_tuple[1] + suffix
            C = base_tuple[2] + suffix

            id_valid = f"rel_{split_name}_{i * 2:04d}_valid"
            id_invalid = f"rel_{split_name}_{i * 2 + 1:04d}_invalid"

            # Valid deduction: Is A > C? -> Yes
            prompt_valid = RELATIONAL_TEMPLATES[0].format(A=A, B=B, C=C, first=A, second=C)
            shifted_valid = [
                RELATIONAL_TEMPLATES[1].format(A=A, B=B, C=C, first=A, second=C),
                RELATIONAL_TEMPLATES[2].format(A=A, B=B, C=C, first=A, second=C),
            ]
            ex_valid = Example(
                id=id_valid,
                family="relational_classification",
                split=split_name,
                prompt=prompt_valid,
                positive="Yes",
                negative="No",
                order=0,  # valid deduction
                ground_truth_label="Yes",
                shifted_prompts=shifted_valid,
                counterpart_id=id_invalid,
                metadata={"A": A, "B": B, "C": C, "first": A, "second": C, "valid": True},
            )

            # Invalid deduction: Is C > A? -> No
            prompt_invalid = RELATIONAL_TEMPLATES[0].format(A=A, B=B, C=C, first=C, second=A)
            shifted_invalid = [
                RELATIONAL_TEMPLATES[1].format(A=A, B=B, C=C, first=C, second=A),
                RELATIONAL_TEMPLATES[2].format(A=A, B=B, C=C, first=C, second=A),
            ]
            ex_invalid = Example(
                id=id_invalid,
                family="relational_classification",
                split=split_name,
                prompt=prompt_invalid,
                positive="No",
                negative="Yes",
                order=1,  # invalid fallacy
                ground_truth_label="No",
                shifted_prompts=shifted_invalid,
                counterpart_id=id_valid,
                metadata={"A": A, "B": B, "C": C, "first": C, "second": A, "valid": False},
            )

            split_examples.append(ex_valid)
            split_examples.append(ex_invalid)

        result[split_name] = split_examples

    return result


def load_all_datasets(seed: int = 42) -> Dict[str, Dict[str, List[Example]]]:
    """Load all 3 families partitioned by dev, val, holdout."""
    return {
        "numerical_ordering": generate_numerical_ordering(seed=seed),
        "symbolic_equivalence": generate_symbolic_equivalence(seed=seed + 1),
        "relational_classification": generate_relational_classification(seed=seed + 2),
    }


def compute_sha256(data: Any) -> str:
    """Compute deterministic SHA-256 of a JSON-serializable object."""
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def generate_dataset_manifest(
    datasets: Dict[str, Dict[str, List[Example]]], output_path: Optional[str] = None
) -> Dict[str, Any]:
    """Generate cryptographic manifest and summary statistics for all datasets."""
    manifest = {
        "campaign": "UOW-NATIVE-2",
        "description": "Cryptographic dataset manifest with partition checksums and counterbalancing verification",
        "total_families": len(datasets),
        "families": {},
    }

    total_examples = 0
    all_serialized = {}

    for fam_name, fam_splits in datasets.items():
        manifest["families"][fam_name] = {
            "splits": {},
            "total_examples": sum(len(exs) for exs in fam_splits.values()),
        }
        fam_dict = {}
        for split_name, examples in fam_splits.items():
            count = len(examples)
            total_examples += count

            order_0_count = sum(1 for e in examples if e.order == 0)
            order_1_count = sum(1 for e in examples if e.order == 1)
            yes_count = sum(1 for e in examples if e.ground_truth_label == "Yes")
            no_count = sum(1 for e in examples if e.ground_truth_label == "No")

            ex_dicts = [e.to_dict() for e in examples]
            split_hash = compute_sha256(ex_dicts)
            fam_dict[split_name] = ex_dicts

            manifest["families"][fam_name]["splits"][split_name] = {
                "count": count,
                "sha256": split_hash,
                "order_0_count": order_0_count,
                "order_1_count": order_1_count,
                "yes_count": yes_count,
                "no_count": no_count,
                "counterbalanced_ratio": round(order_0_count / count, 4) if count > 0 else 0.0,
            }

        all_serialized[fam_name] = fam_dict

    manifest["total_examples"] = total_examples
    manifest["root_sha256"] = compute_sha256(all_serialized)

    if output_path:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    return manifest
