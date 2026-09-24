# Ontology Semantics

Status: R7 additive specification surface.

The current qualified experiments assume a stable semantic vocabulary. A4 is the conceptual next frontier: controlled ontology adaptation.

A4 is **not qualified**.

Therefore this surface defines only forward-compatibility requirements for the reduced architecture.

## Current requirement

For a fixed ontology version:

[
Meaning(x, O_k)
]

must be deterministic and replayable.

## Future A4 requirement

A future ontology transition:

[
O_k ightarrow O_{k+1}
]

must eventually be able to carry:
- explicit authority;
- migration lineage;
- compatibility rules;
- rejection rules;
- versioned semantic identity;
- preservation/reconstruction of prior experiment meaning.

## Reduction constraint

Do not make today's Python enums, dataclass names, or module paths the universal ontology protocol.

The architecture may expose concrete language bindings, but semantic identity must be versioned independently of one language representation.

No ontology mutation behavior is claimed by the current R7 work.
