# UOW-NATIVE-2 Charter: Behavioral Competence and Coordinated Circuit Identification

**Status:** ACTIVE RESEARCH CHARTER  
**Repository:** `NB11B/UoW-v3`  
**Branch:** `research/uow-native-2-circuit-qualification`  
**Reference Baseline:** UOW-NATIVE-1 sealed commit `0dc8d57` (read-only historical evidence)  
**Target Model:** `HuggingFaceTB/SmolLM2-135M-Instruct`  
**Pinned Revision SHA:** `12fd25f77366fa6b3b4b768ec3050bf629380bac`  

---

## 1. Objective and Research Hypothesis

The central question of UOW-NATIVE-2 is:
> *Does a frozen small pretrained language model contain coordinated neural mechanisms that perform a measurable relational computation, and can those mechanisms be bounded as unprivileged probabilistic components within the deterministic UoW architecture?*

### Methodological Invariant: Behavioral Competence Precedes Mechanistic Circuit Search
In UOW-NATIVE-1, single-neuron intervention failed partly because the underlying model exhibited a presentation-order primacy bias ($\approx 42\%$ accuracy) rather than performing genuine magnitude comparison. 
**Rule:** We do not search for the neural circuitry responsible for a computation unless the model first demonstrably performs that computation above prespecified competence thresholds on strictly counterbalanced, non-shortcut data.

---

## 2. Experimental Sequence & Fixed Gates

| Gate | Title | Completion Condition | Stop Rule |
|---|---|---|---|
| **Gate B0** | **Behavioral Qualification** | At least one relational task family achieves $\ge 85\%$ holdout accuracy, $\ge 80\%$ shifted-template accuracy, and $\le 10$ percentage-point positional gap. | If all 3 families fail, halt mechanistic search (B1/B2) and record `BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED`. |
| **Gate B1** | **Circuit Discovery** | Identify candidate cooperating components (layers, token positions, groups of 4, 8, 16 neurons) from development data only. | Conditioned on B0 passing. |
| **Gate B2** | **Causal Falsification** | Evaluate candidate circuit on untouched holdout data against 32 matched random-group controls and activation restoration. | Conditioned on B1 completion. |
| **Gate B3** | **UoW Authority Integration** | Verify deterministic UoW v3 kernel (`src/uow/engine.py`): zero unauthorized commits, fail-closed rejection on invalid proposals. | Independent architectural gate. |
| **Gate B4** | **Efficiency & Reproducibility** | Three independently seeded runs, measured execution time, preserved SHA provenance and cryptographic evidence ledger. | Terminal evidence closure. |

---

## 3. The Three Relational Task Families

1. **Numerical Ordering**:
   - Task: "Which number is larger: {a} or {b}?"
   - Shortcut Control: Counterbalanced operand presentation order.
2. **Symbolic Equivalence**:
   - Task: Evaluate commutative vs non-commutative algebraic equivalence under specified operations.
   - Shortcut Control: Counterbalanced "Yes"/"No" ground truth, randomized symbol names, balanced operator presentation.
3. **Relational Classification**:
   - Task: Transitive relation inference ($A > B \land B > C \implies A > C$) vs invalid fallacies ($C > A$).
   - Shortcut Control: Randomized entity identifiers, balanced valid/invalid inferences.

For each family: 600 independent problem instances partitioned into 200 Development, 200 Validation, and 200 Final Holdout.

---

## 4. Scope Exclusions & Project Boundaries
* Qualified production UoW protocol, transport, and replication remain completely unmodified.
* This research branch remains unmerged.
* No claims of single-neuron standalone execution or SAE replication.
* Honest reporting of both positive and negative findings.
