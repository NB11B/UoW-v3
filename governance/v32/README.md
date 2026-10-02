# UoW v3.2 Deficit-Driven Development Governance

This directory contains the machine-enforceable governance machinery for **Unit-of-Work v3.2**.

Under the v3.2 governance policy, **v3.2 has no predetermined feature list**. New architectural or runtime work is permitted strictly upon the intake, reproduction, and falsification of a concrete deficit witness.

---

## Governing Invariant

\[
\boxed{
\Delta \text{Architecture} = 0
\quad\text{unless}\quad
D(W) > 0
}
\]

where \(D(W)\) is an observed, reproduced semantic, operational, or substrate deficit.
\[
D(W) = 0 \implies \text{no architecture change}
\]

---

## Directory Structure

```text
governance/v32/
├── README.md               # This specification document
├── WITNESS_TEMPLATE.yaml   # Canonical YAML template for all deficit witnesses
└── witnesses/              # Registry of concrete, reviewed witness records
    └── README.md           # Witness registry guidelines
```

---

## Permitted Deficit Categories

Every witness must classify its deficit into **exactly one** of three canonical categories:

1. **`MISSING_ARCHITECTURAL_PRIMITIVE`**:
   The requirement cannot be represented, certified, or committed using the existing canonical 11 protocol objects and operators.
2. **`BOUNDARY_FAILURE_NEW_CONDITION`**:
   A previously qualified invariant actually fails under a newly demonstrated, reproducible stress, scale, partition, or environmental condition.
3. **`SUBSTRATE_REALIZATION_INCOMPATIBILITY`**:
   The existing protocol is semantically expressible, but cannot be correctly enforced on a specific target silicon or hardware authority using current realization mechanisms.

---

## Witness Lifecycle

\[
\boxed{
\text{INTAKE}
\longrightarrow
\text{REPRODUCED}
\longrightarrow
\text{FALSIFICATION}
\longrightarrow
\text{DISPOSITION}
}
\]

Only one terminal path authorizes architectural work:

\[
\boxed{
\text{concrete witness} + \text{reproduction} + \text{failed sufficiency hypothesis } (H_0 \text{ rejected})
\longrightarrow
\text{QUALIFIES}
}
\]

All other dispositions terminate without architectural modification:
- `NO_DEFICIT` \(\longrightarrow\) Close witness (no work).
- `EXISTING_ARCHITECTURE_SUFFICIENT` \(\longrightarrow\) Close witness (document usage).
- `PATCH_ONLY` \(\longrightarrow\) Implementation bugfix route (no protocol/architecture expansion).

See [**`docs/V32_GOVERNANCE.md`**](../../docs/V32_GOVERNANCE.md) for the full operational governance policy and validator tooling.
