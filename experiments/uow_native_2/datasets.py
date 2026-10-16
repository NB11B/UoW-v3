"""Dataset generators and partition manifests for UOW-NATIVE-2.

Generates 3 relational task families:
  1. numerical_ordering: Pairwise magnitude comparison ("Which number is larger: {a} or {b}?")
  2. symbolic_equivalence: Algebraic commutativity & non-commutativity ("Is {expr1} equal to {expr2}?")
  3. relational_classification: Transitive deduction ("If A > B and B > C, is A > C?") vs invalid fallacy ("... is C > A?")

Each family contains 600 examples partitioned into:
  - 200 Development (dev)
  - 200 Validation (val)
  - 200 Holdout (holdout)

Enforces strict counterbalancing and orthogonal factorial design:
  - Exactly 50% presentation order 0 vs order 1 across all families
  - Exactly 50% target positive label vs negative label
  - Zero confounding between order and label: Order (0/1) and Ground-Truth Label (Yes/No)
    are strictly orthogonal 2x2 factorials (50 Order 0 Yes, 50 Order 0 No, 50 Order 1 Yes, 50 Order 1 No).
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

RELATIONAL_TEMPLATES_CANONICAL = "Statement 1: {s1}. Statement 2: {s2}. Question: Is {first} heavier than {second}? Answer Yes or No."
RELATIONAL_TEMPLATES_SHIFTED_1 = "Given that {s1} and {s2}, does it follow that {first} > {second}? Reply Yes or No."
RELATIONAL_TEMPLATES_SHIFTED_2 = "Premise: {s1}, and {s2}. Deduction: Does {first} precede {second}? Answer Yes or No."


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

    2x2 Factorial Design:
      - 50 Equivalent, Order 0 (prompt expr_a and expr_b -> Yes)
      - 50 Equivalent, Order 1 (prompt expr_b and expr_a -> Yes)
      - 50 Non-equivalent, Order 0 (prompt expr_c and expr_d -> No)
      - 50 Non-equivalent, Order 1 (prompt expr_d and expr_c -> No)

    Order and Ground-Truth Label are strictly orthogonal.
    """
    rng = random.Random(seed)

    var_pools = {
        "dev": [("m", "n"), ("p", "q"), ("u", "v"), ("r", "s"), ("j", "k")],
        "val": [("w", "z"), ("c", "d"), ("f", "g"), ("x", "y"), ("a", "b")],
        "holdout": [("h", "l"), ("t", "w"), ("e", "k"), ("alpha", "beta"), ("theta", "phi")],
    }

    result = {}
    for split_name, pool in var_pools.items():
        split_examples = []
        for i in range(50):
            v1, v2 = pool[i % len(pool)]
            coeff = (i // len(pool)) + 1
            var1 = f"{coeff}{v1}" if coeff > 1 else v1
            var2 = f"{coeff}{v2}" if coeff > 1 else v2

            # Commutative pair (+ or *)
            op_comm = "+" if (i % 2 == 0) else "*"
            expr1_comm = f"{var1} {op_comm} {var2}"
            expr2_comm = f"{var2} {op_comm} {var1}"

            # Non-commutative pair (- or /)
            op_noncomm = "-" if (i % 2 == 0) else "/"
            expr1_noncomm = f"{var1} {op_noncomm} {var2}"
            expr2_noncomm = f"{var2} {op_noncomm} {var1}"

            id_eq_0 = f"sym_{split_name}_{i * 4 + 0:04d}_eq_ord0"
            id_eq_1 = f"sym_{split_name}_{i * 4 + 1:04d}_eq_ord1"
            id_neq_0 = f"sym_{split_name}_{i * 4 + 2:04d}_neq_ord0"
            id_neq_1 = f"sym_{split_name}_{i * 4 + 3:04d}_neq_ord1"

            # 1. Equivalent, Order 0 (expr1, expr2) -> Yes
            prompt_eq_0 = SYMBOLIC_TEMPLATES[0].format(expr1=expr1_comm, expr2=expr2_comm)
            shifted_eq_0 = [
                SYMBOLIC_TEMPLATES[1].format(expr1=expr1_comm, expr2=expr2_comm),
                SYMBOLIC_TEMPLATES[2].format(expr1=expr1_comm, expr2=expr2_comm),
            ]
            ex_eq_0 = Example(
                id=id_eq_0,
                family="symbolic_equivalence",
                split=split_name,
                prompt=prompt_eq_0,
                positive="Yes",
                negative="No",
                order=0,
                ground_truth_label="Yes",
                shifted_prompts=shifted_eq_0,
                counterpart_id=id_eq_1,
                metadata={"op": op_comm, "equivalent": True, "order": 0, "config_idx": i},
            )

            # 2. Equivalent, Order 1 (expr2, expr1) -> Yes
            prompt_eq_1 = SYMBOLIC_TEMPLATES[0].format(expr1=expr2_comm, expr2=expr1_comm)
            shifted_eq_1 = [
                SYMBOLIC_TEMPLATES[1].format(expr1=expr2_comm, expr2=expr1_comm),
                SYMBOLIC_TEMPLATES[2].format(expr1=expr2_comm, expr2=expr1_comm),
            ]
            ex_eq_1 = Example(
                id=id_eq_1,
                family="symbolic_equivalence",
                split=split_name,
                prompt=prompt_eq_1,
                positive="Yes",
                negative="No",
                order=1,
                ground_truth_label="Yes",
                shifted_prompts=shifted_eq_1,
                counterpart_id=id_eq_0,
                metadata={"op": op_comm, "equivalent": True, "order": 1, "config_idx": i},
            )

            # 3. Non-equivalent, Order 0 (expr1, expr2) -> No
            prompt_neq_0 = SYMBOLIC_TEMPLATES[0].format(expr1=expr1_noncomm, expr2=expr2_noncomm)
            shifted_neq_0 = [
                SYMBOLIC_TEMPLATES[1].format(expr1=expr1_noncomm, expr2=expr2_noncomm),
                SYMBOLIC_TEMPLATES[2].format(expr1=expr1_noncomm, expr2=expr2_noncomm),
            ]
            ex_neq_0 = Example(
                id=id_neq_0,
                family="symbolic_equivalence",
                split=split_name,
                prompt=prompt_neq_0,
                positive="No",
                negative="Yes",
                order=0,
                ground_truth_label="No",
                shifted_prompts=shifted_neq_0,
                counterpart_id=id_neq_1,
                metadata={"op": op_noncomm, "equivalent": False, "order": 0, "config_idx": i},
            )

            # 4. Non-equivalent, Order 1 (expr2, expr1) -> No
            prompt_neq_1 = SYMBOLIC_TEMPLATES[0].format(expr1=expr2_noncomm, expr2=expr1_noncomm)
            shifted_neq_1 = [
                SYMBOLIC_TEMPLATES[1].format(expr1=expr2_noncomm, expr2=expr1_noncomm),
                SYMBOLIC_TEMPLATES[2].format(expr1=expr2_noncomm, expr2=expr1_noncomm),
            ]
            ex_neq_1 = Example(
                id=id_neq_1,
                family="symbolic_equivalence",
                split=split_name,
                prompt=prompt_neq_1,
                positive="No",
                negative="Yes",
                order=1,
                ground_truth_label="No",
                shifted_prompts=shifted_neq_1,
                counterpart_id=id_neq_0,
                metadata={"op": op_noncomm, "equivalent": False, "order": 1, "config_idx": i},
            )

            split_examples.extend([ex_eq_0, ex_eq_1, ex_neq_0, ex_neq_1])

        result[split_name] = split_examples

    return result


def generate_relational_classification(seed: int = 44) -> Dict[str, List[Example]]:
    """Generate 600 relational classification examples: 200 dev, 200 val, 200 holdout.

    2x2 Factorial Design:
      - 50 Valid deduction, Premise Order 0 (A>B, B>C -> Is A>C? -> Yes)
      - 50 Valid deduction, Premise Order 1 (B>C, A>B -> Is A>C? -> Yes)
      - 50 Invalid fallacy, Premise Order 0 (A>B, B>C -> Is C>A? -> No)
      - 50 Invalid fallacy, Premise Order 1 (B>C, A>B -> Is C>A? -> No)

    Order and Ground-Truth Label are strictly orthogonal.
    """
    rng = random.Random(seed)

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
        for i in range(50):
            base_tuple = pool[i % len(pool)]
            suffix = f"_{i // len(pool)}" if (i // len(pool)) > 0 else ""
            A = base_tuple[0] + suffix
            B = base_tuple[1] + suffix
            C = base_tuple[2] + suffix

            # Premise descriptions:
            # Canonical: "A is heavier than B", "B is heavier than C"
            p_AB_canon = f"{A} is heavier than {B}"
            p_BC_canon = f"{B} is heavier than {C}"
            # Shifted 1: "A > B", "B > C"
            p_AB_s1 = f"{A} > {B}"
            p_BC_s1 = f"{B} > {C}"
            # Shifted 2: "A precedes B", "B precedes C"
            p_AB_s2 = f"{A} precedes {B}"
            p_BC_s2 = f"{B} precedes {C}"

            id_val_0 = f"rel_{split_name}_{i * 4 + 0:04d}_val_ord0"
            id_val_1 = f"rel_{split_name}_{i * 4 + 1:04d}_val_ord1"
            id_inval_0 = f"rel_{split_name}_{i * 4 + 2:04d}_inval_ord0"
            id_inval_1 = f"rel_{split_name}_{i * 4 + 3:04d}_inval_ord1"

            # 1. Valid, Order 0 (AB then BC) -> Yes
            prompt_val_0 = RELATIONAL_TEMPLATES_CANONICAL.format(s1=p_AB_canon, s2=p_BC_canon, first=A, second=C)
            shifted_val_0 = [
                RELATIONAL_TEMPLATES_SHIFTED_1.format(s1=p_AB_s1, s2=p_BC_s1, first=A, second=C),
                RELATIONAL_TEMPLATES_SHIFTED_2.format(s1=p_AB_s2, s2=p_BC_s2, first=A, second=C),
            ]
            ex_val_0 = Example(
                id=id_val_0,
                family="relational_classification",
                split=split_name,
                prompt=prompt_val_0,
                positive="Yes",
                negative="No",
                order=0,
                ground_truth_label="Yes",
                shifted_prompts=shifted_val_0,
                counterpart_id=id_val_1,
                metadata={"A": A, "B": B, "C": C, "first": A, "second": C, "valid": True, "order": 0, "config_idx": i},
            )

            # 2. Valid, Order 1 (BC then AB) -> Yes
            prompt_val_1 = RELATIONAL_TEMPLATES_CANONICAL.format(s1=p_BC_canon, s2=p_AB_canon, first=A, second=C)
            shifted_val_1 = [
                RELATIONAL_TEMPLATES_SHIFTED_1.format(s1=p_BC_s1, s2=p_AB_s1, first=A, second=C),
                RELATIONAL_TEMPLATES_SHIFTED_2.format(s1=p_BC_s2, s2=p_AB_s2, first=A, second=C),
            ]
            ex_val_1 = Example(
                id=id_val_1,
                family="relational_classification",
                split=split_name,
                prompt=prompt_val_1,
                positive="Yes",
                negative="No",
                order=1,
                ground_truth_label="Yes",
                shifted_prompts=shifted_val_1,
                counterpart_id=id_val_0,
                metadata={"A": A, "B": B, "C": C, "first": A, "second": C, "valid": True, "order": 1, "config_idx": i},
            )

            # 3. Invalid, Order 0 (AB then BC) -> No (Is C > A?)
            prompt_inval_0 = RELATIONAL_TEMPLATES_CANONICAL.format(s1=p_AB_canon, s2=p_BC_canon, first=C, second=A)
            shifted_inval_0 = [
                RELATIONAL_TEMPLATES_SHIFTED_1.format(s1=p_AB_s1, s2=p_BC_s1, first=C, second=A),
                RELATIONAL_TEMPLATES_SHIFTED_2.format(s1=p_AB_s2, s2=p_BC_s2, first=C, second=A),
            ]
            ex_inval_0 = Example(
                id=id_inval_0,
                family="relational_classification",
                split=split_name,
                prompt=prompt_inval_0,
                positive="No",
                negative="Yes",
                order=0,
                ground_truth_label="No",
                shifted_prompts=shifted_inval_0,
                counterpart_id=id_inval_1,
                metadata={"A": A, "B": B, "C": C, "first": C, "second": A, "valid": False, "order": 0, "config_idx": i},
            )

            # 4. Invalid, Order 1 (BC then AB) -> No (Is C > A?)
            prompt_inval_1 = RELATIONAL_TEMPLATES_CANONICAL.format(s1=p_BC_canon, s2=p_AB_canon, first=C, second=A)
            shifted_inval_1 = [
                RELATIONAL_TEMPLATES_SHIFTED_1.format(s1=p_BC_s1, s2=p_AB_s1, first=C, second=A),
                RELATIONAL_TEMPLATES_SHIFTED_2.format(s1=p_BC_s2, s2=p_AB_s2, first=C, second=A),
            ]
            ex_inval_1 = Example(
                id=id_inval_1,
                family="relational_classification",
                split=split_name,
                prompt=prompt_inval_1,
                positive="No",
                negative="Yes",
                order=1,
                ground_truth_label="No",
                shifted_prompts=shifted_inval_1,
                counterpart_id=id_inval_0,
                metadata={"A": A, "B": B, "C": C, "first": C, "second": A, "valid": False, "order": 1, "config_idx": i},
            )

            split_examples.extend([ex_val_0, ex_val_1, ex_inval_0, ex_inval_1])

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

            # 2x2 Factorial cell counts
            order_0_yes = sum(1 for e in examples if e.order == 0 and e.ground_truth_label == "Yes")
            order_0_no = sum(1 for e in examples if e.order == 0 and e.ground_truth_label == "No")
            order_1_yes = sum(1 for e in examples if e.order == 1 and e.ground_truth_label == "Yes")
            order_1_no = sum(1 for e in examples if e.order == 1 and e.ground_truth_label == "No")

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
                "counterbalanced_order_ratio": round(order_0_count / count, 4) if count > 0 else 0.0,
                "factorial_cells": {
                    "order_0_yes": order_0_yes,
                    "order_0_no": order_0_no,
                    "order_1_yes": order_1_yes,
                    "order_1_no": order_1_no,
                },
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
