# JEV x UoW Failure Semantics Operator Family Identification Campaign

## 1. Experimental Question & Framing

Does JEV resolve distinct governed failure mechanisms into distinct, reproducible operator directions, or do all failure mechanisms collapse to a generic one-dimensional governance-failure macrostate?

$$\boxed{\text{\textbf{Does JEV resolve distinct governed failure mechanisms into distinct, reproducible operator directions?}}}$$

In previous campaigns, we established that:
- Post-threshold authority-loss geometry $\Delta_A^*$ is size-independent ($M \in \{8, 16, 32\}$) and invariant across five realization topologies ($\min \cos \ge 0.9988$).
- Quorum governance enforces a sharp, discontinuous transition jump ($J^* \approx +1.35$) and subcritical shielding ($S^* \approx 7.0\times$).

However, all prior failure runs tested the **same failure mechanism**: leaf verifier unbinding / authority loss ($\Delta_A$). 

The current campaign estimates the **operator family**:
$$\mathcal{F} = \{\Delta_A, \Delta_E, \Delta_C, \Delta_T, \Delta_R, \Delta_{\mathrm{Adv}}\}$$
under a single, strictly fixed architecture:
- Fixed ensemble size: $M = 16$
- Fixed quorum requirement: $Q = 9$
- Fixed realization topology: Star fan-out (direct independent lines)
- Fixed recursive depth: $d = 1$
- Pinned model: `jev-1.13.0`, 3 replicates per state (39 live requests total)

### Dual Scientific Hypotheses
1. **Generic Macrostate Attractor Hypothesis**: Conditioned on the inability of the unit to complete lawfully, all failure mechanisms collapse toward a common single attractor:
   $$\cos(\Delta_i, \Delta_j) \ge 0.950 \quad \forall i, j \in \mathcal{F}$$
   Under this outcome, JEV measures only an undifferentiated binary macrostate (governed vs. ungoverned).
2. **Mechanism-Resolving Operator Family Hypothesis**: Conditioned on the *identical* unfulfillable macro-outcome, JEV resolves distinct failure mechanisms into distinct, reproducible operator directions:
   $$\min_{i \neq j} \cos(\Delta_i, \Delta_j) < 0.950 \quad (\text{or pairwise separation angle } \theta_{ij} > 20^\circ)$$
   Under this outcome:
   $$\boxed{\text{\textbf{Conditioned on the same failed macro-outcome, JEV preserves information about failure mechanism.}}}$$

---

## 2. Orthogonalized Failure Mechanisms

To prevent accidentally measuring the same deterministic consequence under different names, the six failure mechanisms are mutually exclusive and cleanly orthogonalized:

1. **$\Delta_A$ (Authority Loss)**:
   - Verifier role unassigned / binding revoked.
   - Evidence records, causal graph, resources, and timing are otherwise intact.
2. **$\Delta_E$ (Evidence Integrity Corruption)**:
   - Execution pipeline completes and authority binding is valid, but cryptographic hash-chain / digest integrity check fails.
   - Causal graph, resources, and timing are intact.
3. **$\Delta_C$ (Causal Severance)**:
   - Authority is valid and evidence mechanism intact, but a required causal dependency edge is structurally broken (missing predecessor). Execution halts early at severed boundary.
4. **$\Delta_T$ (Temporal Expiration / Stale Evidence)**:
   - Authority, evidence records, and causality are valid, but execution timestamp exceeds the parent contract deadline ($2850\,\text{ms} > 1000\,\text{ms}$).
5. **$\Delta_R$ (Resource Legality Violation)**:
   - Authority, evidence, causality, and timing remain intact, but memory consumption exceeds the legal resource envelope ($64\,\text{RAM} > 16\,\text{RAM}$), forcing rollback.
6. **$\Delta_{\mathrm{Adv}}$ (Adversarial False Evidence Conflict)**:
   - Dual conflicting validly-signed attestations are presented from uncoordinated actors, triggering deterministic quarantine rather than ordinary corruption.

### Common-Output Control
Every failure state in $\mathcal{F}$ produces the exact same high-level macroscopic outcome:
- Admissible certified units: $8 < 9 \implies$ Quorum margin: $-1$
- Emitted output keys: `[]` (strictly empty)
- Deterministic oracle status: `FAILED`

If JEV separates these operators, it demonstrates that its representation does not merely classify `SUCCESS` vs. `FAILURE`, but encodes the underlying cybernetic failure mechanism.

---

## 3. Sequential Composition & Noncommutativity

Only after identifying distinct operators does composition ordering become meaningful:
$$\boxed{\text{operator separation} \longrightarrow \text{composition} \longrightarrow \text{noncommutativity} \longrightarrow \text{closure test}}$$

For two failure operators $F_i, F_j$, we evaluate the directional composition $F_i F_j$ against $F_j F_i$:
- **Pair 1: Authority vs. Evidence** (`comp_AE` vs. `comp_EA`):
  $F_A F_E$: Authority missing at verification stage $\implies$ evidence unverified.
  $F_E F_A$: Evidence corrupted early at dispatch $\implies$ execution aborts before authority evaluation.
- **Pair 2: Authority vs. Causal** (`comp_AC` vs. `comp_CA`):
  $F_A F_C$: Authority unbinding occurs after full causal traversal to aggregator.
  $F_C F_A$: Causal break severs pipeline at parse stage $\implies$ halts before authority can be queried.
- **Pair 3: Evidence vs. Resource** (`comp_ER` vs. `comp_RE`):
  $F_E F_R$: Evidence corruption occurs at routing $\implies$ halts before resource ceiling is reached.
  $F_R F_E$: Resource ceiling breached early at parse stage $\implies$ halts before evidence generation.

We measure empirical noncommutativity:
$$\kappa_{ij} = \|\Delta_{ij} - \Delta_{ji}\|$$
relative to within-state repeatability noise $\sigma_{\text{rep}}$:
$$\eta_{ij} = \frac{\kappa_{ij}}{\sigma_{\text{rep}}}$$
If $\eta_{ij} \ge 3.0\times$, noncommutativity is statistically significant over repeatability noise.

---

## 4. 13 Preregistered States Specification Table

| Spec ID | Mechanism | Role | Disturbed ($k$) | Admissible ($N_{\text{adm}}$) | Margin | Regime | Sequence ($F_i \circ F_j$) | Expected Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `op_base` | Nominal / None | `base` | 0 | 16 | +7 | Quorum | — | `SUCCESS` |
| `op_A` | Authority Loss | `operator` | 8 | 8 | -1 | Quorum | — | `FAILED` |
| `op_E` | Evidence Corruption | `operator` | 8 | 8 | -1 | Quorum | — | `FAILED` |
| `op_C` | Causal Severance | `operator` | 8 | 8 | -1 | Quorum | — | `FAILED` |
| `op_T` | Temporal Expiration | `operator` | 8 | 8 | -1 | Quorum | — | `FAILED` |
| `op_R` | Resource Breach | `operator` | 8 | 8 | -1 | Quorum | — | `FAILED` |
| `op_Adv` | Adversarial Conflict | `operator` | 8 | 8 | -1 | Quorum | — | `FAILED` |
| `comp_AE` | Authority then Evidence | `composition` | 8 | 8 | -1 | Quorum | $F_A \circ F_E$ | `FAILED` |
| `comp_EA` | Evidence then Authority | `composition` | 8 | 8 | -1 | Quorum | $F_E \circ F_A$ | `FAILED` |
| `comp_AC` | Authority then Causal | `composition` | 8 | 8 | -1 | Quorum | $F_A \circ F_C$ | `FAILED` |
| `comp_CA` | Causal then Authority | `composition` | 8 | 8 | -1 | Quorum | $F_C \circ F_A$ | `FAILED` |
| `comp_ER` | Evidence then Resource | `composition` | 8 | 8 | -1 | Quorum | $F_E \circ F_R$ | `FAILED` |
| `comp_RE` | Resource then Evidence | `composition` | 8 | 8 | -1 | Quorum | $F_R \circ F_E$ | `FAILED` |

### Evaluation Budget
- 13 States × 3 Replicates = **39 live requests**
- Model pinned: `jev-1.13.0`
- Zero outcome labels: raw telemetry strictly bans all forbidden substrings.

---

## 5. Preregistered Engineering Gates

- **U0 Deterministic Oracle Conformance**: All 13 states execute in accordance with their respective failure contract. All boundary certificates remain valid.
- **J0 Provider Completeness**: All 39 live requests return valid 8-D probability vectors.
- **J1 Operator Detectability**: Every failure operator $\Delta_i$ satisfies $\text{SNR}_i = \frac{\|\Delta_i\|}{\sigma_{\text{rep}}} \ge 10.0\times$.
- **J2 Repeatability Noise Floor**: Median replicate noise satisfies $\sigma_{\text{rep}} \le 0.050$.
- **J3 Operator Family Characterization**: Complete the pairwise cosine matrix $C_{ij}$ and determine whether $\mathcal{F}$ exhibits multi-operator separation ($\min_{i \neq j} C_{ij} < 0.950$) or generic macrostate collapse ($\min C_{ij} \ge 0.950$).
- **J4 Noncommutativity Evaluation**: For all three composed pairs, evaluate $\kappa_{ij}$ and ratio $\eta_{ij} = \kappa_{ij}/\sigma_{\text{rep}}$ to determine whether composition is commutative or non-Abelian.

---

## 6. Live Empirical Results (Run 2026-09-26)

All 39 live requests were executed against pinned `jev-1.13.0` via `typesafe-sdk==0.7.1` (13 states × 3 replicates).

### 6.1 Gate Scorecard

| Gate | Description | Preregistered Criterion | Empirical Value | Status |
| :--- | :--- | :---: | :---: | :---: |
| **U0** | **Deterministic Oracle Conformance** | 100% valid execution & certificates | 13 / 13 valid | **PASS** |
| **J0** | **Provider Completeness** | 39 / 39 valid 8-D vectors | 39 / 39 valid | **PASS** |
| **J1** | **Operator Detectability** | $\text{SNR}_i \ge 10.0\times$ for all six failure modes | **64.4× ($\Delta_A$) to 74.2× ($\Delta_E$)** | **PASS** |
| **J2** | **Repeatability Noise Floor** | $\sigma_{\text{rep}} \le 0.050$ | **$\sigma_{\text{rep}} = 0.0238$** | **PASS** |
| **J3** | **Operator Family Characterization** | Evaluate pairwise cosine matrix $C_{ij}$ | **$\min C_{ij} = 0.9854$, mean $0.9943$** | **PASS** |
| **J4** | **Noncommutativity Evaluation** | Evaluate $\kappa_{ij}$ and ratio $\eta_{ij}$ for 3 pairs | **$\eta \in [6.24\times, 7.85\times]$ (All Significant)** | **PASS** |

**Final Verdict**: `SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES`

---

### 6.2 Pure Failure Operator Metrics ($\mathcal{F}$)

All evaluated at identical leaf disturbance count $k = 8$ ($M = 16, Q = 9$, quorum margin $-1$, uncommitted):

| Failure Operator | Mechanism | Displacement Norm $\|\Delta_i\|$ | Signal-to-Noise Ratio ($\text{SNR}_i$) | Observable Profile Focus |
| :--- | :--- | :---: | :---: | :--- |
| **$\Delta_A$** | Authority Loss | 1.5341 | **64.4×** | Authority binding unassigned; evidence/causal/timing intact |
| **$\Delta_E$** | Evidence Corruption | 1.7657 | **74.2×** | Cryptographic digest mismatch; authority/causal/timing intact |
| **$\Delta_C$** | Causal Severance | 1.5853 | **66.6×** | Missing dependency edge; pipeline halted at dispatch |
| **$\Delta_T$** | Temporal Expiration | 1.6288 | **68.4×** | Timestamp exceeded contract limit ($2850\,\text{ms} > 1000\,\text{ms}$) |
| **$\Delta_R$** | Resource Breach | 1.6433 | **69.0×** | Memory envelope exceeded ($64\,\text{RAM} > 16\,\text{RAM}$) |
| **$\Delta_{\mathrm{Adv}}$** | Adversarial Conflict | 1.7517 | **73.6×** | Conflicting attestations; deterministic quarantine active |

- **Mean Operator Norm**: $\|\bar{\Delta}\| = 1.6515 \pm 0.0847$ ($CV = 5.1\%$)
- **Repeatability Noise Floor**: $\sigma_{\text{rep}} = 0.0238$

---

### 6.3 Pairwise Operator Directional Cosine Matrix ($C_{ij}$) & Separation Angles

Pairwise cosine similarities $C_{ij} = \cos(\Delta_i, \Delta_j)$ and separation angles $\theta_{ij} = \arccos(C_{ij})$:

| | $\Delta_A$ | $\Delta_E$ | $\Delta_C$ | $\Delta_T$ | $\Delta_R$ | $\Delta_{\mathrm{Adv}}$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **$\Delta_A$** | 1.0000 | 0.9949 ($5.8^\circ$) | 0.9987 ($3.0^\circ$) | 0.9944 ($6.1^\circ$) | 0.9965 ($4.8^\circ$) | 0.9854 ($9.8^\circ$) |
| **$\Delta_E$** | 0.9949 | 1.0000 | 0.9984 ($3.3^\circ$) | 0.9964 ($4.9^\circ$) | 0.9972 ($4.3^\circ$) | 0.9891 ($8.5^\circ$) |
| **$\Delta_C$** | 0.9987 | 0.9984 | 1.0000 | 0.9973 ($4.2^\circ$) | 0.9979 ($3.8^\circ$) | 0.9888 ($8.6^\circ$) |
| **$\Delta_T$** | 0.9944 | 0.9964 | 0.9973 | 1.0000 | 0.9987 ($3.0^\circ$) | 0.9917 ($7.4^\circ$) |
| **$\Delta_R$** | 0.9965 | 0.9972 | 0.9979 | 0.9987 | 1.0000 | 0.9896 ($8.3^\circ$) |
| **$\Delta_{\mathrm{Adv}}$** | 0.9854 | 0.9891 | 0.9888 | 0.9917 | 0.9896 | 1.0000 |

- **Minimum Pairwise Cosine**: **0.9854** ($\Delta_A$ vs. $\Delta_{\mathrm{Adv}}$)
- **Mean Pairwise Cosine**: **0.9943**
- **Maximum Separation Angle**: **9.80°** ($\Delta_A$ vs. $\Delta_{\mathrm{Adv}}$)
- **Regime**: **`GENERIC_FAILURE_MACROSTATE_ATTRACTOR`**

---

### 6.4 Sequential Composition & Empirical Noncommutativity

For each candidate pair $(F_i, F_j)$, we compare the directional compositions $F_i F_j$ vs. $F_j F_i$:

| Composition Pair | Sequences Compared | Noncommutativity $\kappa_{ij} = \|\Delta_{ij} - \Delta_{ji}\|$ | Noise Floor $\sigma_{\text{rep}}$ | Ratio $\eta_{ij} = \kappa_{ij}/\sigma_{\text{rep}}$ | Directional Cosine $\cos(\Delta_{ij}, \Delta_{ji})$ | Noncommutative Significance |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Authority vs. Evidence** | `comp_AE` vs. `comp_EA` | **0.1869** | 0.0238 | **7.85×** | 0.9972 | **YES ($\ge 3.0\times$)** |
| **Authority vs. Causal** | `comp_AC` vs. `comp_CA` | **0.1485** | 0.0238 | **6.24×** | 0.9988 | **YES ($\ge 3.0\times$)** |
| **Evidence vs. Resource** | `comp_ER` vs. `comp_RE` | **0.1508** | 0.0238 | **6.34×** | 0.9971 | **YES ($\ge 3.0\times$)** |

---

### 6.5 Cybernetic Findings & Scientific Interpretation

1. **Resolution of the Primary Scientific Question: Generic Macrostate Attractor**:
   When conditioned on the identical unfulfillable commit outcome (uncommitted state, empty emitted keys, quorum margin $-1$), **all six distinct failure mechanisms collapse toward the same universal macrostate attractor direction**:
   $$\min_{i \neq j} \cos(\Delta_i, \Delta_j) = \mathbf{0.9854}, \quad \text{mean } \cos = \mathbf{0.9943}$$
   The separation angles between failure mechanisms are small ($\theta_{ij} \in [2.95^\circ, 9.80^\circ]$).
   
   > [!IMPORTANT] Core Architectural Insight
   > In JEV representation space, governed failure is dominated by the **macroscopic breakdown of the regulatory envelope**, rather than fracturing into a scattered collection of disparate semantic operators. JEV does not perceive failure as a bag of independent, orthogonal causes; it observes that **governance has collapsed**, and projects the state into the universal authority-loss attractor $\Delta_A^*$.

2. **Subtle Mechanism-Specific Deflection (Fine Structure)**:
   While macrostate collapse dominates the global direction ($\ge 98.5\%$ alignment), the fine structure reflects the nature of the breach:
   - **Internal execution failures** (Authority $\Delta_A$, Causal $\Delta_C$, Resource $\Delta_R$, Temporal $\Delta_T$) cluster most tightly ($\cos \ge 0.994$).
   - **Adversarial quarantine** ($\Delta_{\mathrm{Adv}}$) exhibits the largest angular deflection from authority loss ($\theta = 9.80^\circ$, $\cos = 0.9854$), driven by the distinct signature of active divergence quarantine.

3. **Statistically Significant Noncommutativity ($\kappa_{ij} \gg \sigma_{\text{rep}}$)**:
   Despite operating within the common macrostate attractor ($\cos \ge 0.997$ between forward and reverse orders), the **order in which failures are evaluated matters**:
   $$\kappa_{ij} \approx 0.15 - 0.19 \quad \implies \quad \eta_{ij} = \frac{\kappa_{ij}}{\sigma_{\text{rep}}} \in [\mathbf{6.24\times}, \mathbf{7.85\times}]$$
   Because regulatory constraints form a sequential causal pipeline (e.g. an early evidence corruption halts execution before authority can be queried), the compound displacement vector depends on evaluation sequence.
   This provides empirical evidence for **non-Abelian sequential composition** inside the macrostate attractor.

