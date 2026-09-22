# Architecture

## Invariant decomposition

The canonical architecture separates four primitive concerns:

1. **Ontology** — the semantic work pairing.
2. **Contract** — the deterministic transition relation.
3. **State** — immutable, hash-bound authoritative data.
4. **Authority** — PROPOSE -> CERTIFY -> COMMIT with append-only evidence.

Everything else is derived.

## Semantic ontology

The eight categories are:

- People
- Processes
- Data
- Devices
- Rules
- Policies
- Agents
- Guidance

Their Cartesian product yields exactly 64 directed matrix cells.

A matrix cell answers **what kind of work is this?** It does not answer how the
work executes and must never become an opcode table.

## Unit of Work

The canonical envelope remains:

```
U = (H, Gamma, M, R, B, E, T)
```

where H is identity/semantic classification, Gamma is the transition contract,
and M/R/B/E/T carry lifecycle, realization, boundary, evidence, and timing
descriptors without importing runtime implementations into the kernel.

## State

`WorldState` accepts immutable JSON-compatible typed values rather than the
research runtime's integer-only counter schema. This removes a proof-campaign
assumption while keeping canonical serialization and cryptographic hash binding.

The core state intentionally does not contain dedicated queue, active-set,
transaction, resource, model, or external-effect fields. Derived layers may
compose those structures over the primitive state model.

## Successors

Dynamic routing is represented explicitly with `Successor.from_attribute(...)`.
The research sentinel `@DISPATCHED` is not part of the canonical contract.

## Authority boundary

A proposal has no state authority. Certification independently recomputes the
transition from the bound pre-state. Commit accepts only a certificate matching
the exact UoW, pre-state, route, post-state, successor, and halt decision.

This boundary is the stable seam for heuristic, optimization, learned, NPU, or
other probabilistic proposal systems.

## Derived layers

The following are intentionally outside the kernel and will be migrated as
separate packages:

- reflective orchestration and dependency scheduling
- optimistic concurrency control and durable sequencing
- resource requirements and leases
- learned/probabilistic proposer integrations
- goal-driven graph synthesis
- certified external effects, asynchronous receipts, and saga compensation

Correctness dependencies point inward toward the kernel. The kernel must never
import those layers.
