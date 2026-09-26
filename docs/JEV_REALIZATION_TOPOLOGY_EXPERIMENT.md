# JEV x UoW Realization Graph Topology Invariance Campaign

## 1. Experimental Question & Cybernetic Hypothesis

Does the collective cybernetic behavior and failure geometry of a governed UoW ensemble survive when the realization interaction topology is fundamentally altered?

In previous campaigns, we demonstrated that:
1. **Size-Invariance**: Post-threshold authority-loss geometry is size-independent across $M \in \{8, 16, 32\}$ ($\min \cos \ge 0.9979$, $CV \approx 0.37\%$).
2. **Phase Transition**: Quorum governance exhibits a discontinuous jump at threshold $\rho_c$, suppressing subcritical disturbance prior to the transition.

However, in simple homogeneous ensembles, topology was implicit. If we maintain the rule that the parent root only counts valid units directly, graph topology is purely decorative.

To establish genuine **realization topology invariance**, authority and evidence must travel through the realization graph:
$$\boxed{\text{Root remains governed iff it can obtain } Q \text{ valid certified contributions through surviving causal paths}}$$

Under this rule, topology dictates how local disturbances propagate:
- Severing a critical structural bottleneck (e.g., a tree branch sub-aggregator or modular bridge) drops all downstream contributions regardless of their internal validity.
- Dense topologies (small-world shortcuts or chordal bypasses) provide alternative routing, preserving quorum resilience.

We formulate the dual cybernetic hypothesis:
$$\boxed{
\begin{aligned}
\rho_c(T) &\neq \text{const} \quad &&\text{(Effective Resilience is Topology-Dependent)} \\
\Delta_{A,T}^* &\longrightarrow \Delta_A^* \quad &&\text{(Authority-Loss Geometry is Topology-Invariant)}
\end{aligned}
}$$
That is: **Interaction topology and routing determine the critical threshold $\rho_c(T)$ and resilience, but authority loss governs the post-threshold cybernetic attractor geometry.**

---

## 2. Experimental Surface & Parameter Space

The campaign evaluates 18 preregistered states across **five frozen realization topologies**, all operating at fixed ensemble size $M = 16$ and global quorum $Q = 9$:

1. **Star / Fan-Out ($T_{\text{star}}$)**:
   - Direct independent connections from all 16 units to the parent root.
   - Resilience threshold: $\rho_c = 0.500$ ($k_c = 8$).
2. **Hierarchical Balanced Tree ($T_{\text{tree}}$)**:
   - 4 branches of 4 units: $B_0(0..3), B_1(4..7), B_2(8..11), B_3(12..15)$.
   - Each branch requires local quorum $\ge 3$ valid units to certify and report.
   - Cutting 2 units in $B_0$ and 2 units in $B_1$ collapses both branches, dropping reachability from 16 to 8.
   - Resilience threshold: $\rho_c = 0.250$ ($k_c = 4$).
3. **Modular Clusters ($T_{\text{modular}}$)**:
   - 4 clusters of 4 units connected linearly via bridge units: $C_0 \xrightarrow{u_3} C_1 \xrightarrow{u_7} C_2 \xrightarrow{u_{11}} C_3$.
   - Cutting bridge unit $u_{11}$ isolates $C_3$; cutting $u_7$ isolates $C_2$ and $C_3$.
   - Targeted cut of $\{0, 1, 2, 11, 12\}$ severs $C_3$ and leaves only 8 reachable units.
   - Resilience threshold: $\rho_c = 0.3125$ ($k_c = 5$).
4. **Ring with Chordal Bypasses ($T_{\text{ring}}$)**:
   - Ring lattice with chords at step 1 and step 2, routing to dual collectors at nodes 0 and 8.
   - Cutting an arc $\{1, 2, 3, 6, 7, 9\}$ severs chordal pathways, reducing reachability to 8.
   - Resilience threshold: $\rho_c = 0.375$ ($k_c = 6$).
5. **Small-World Network ($T_{\text{sw}}$)**:
   - Ring lattice augmented with 4 frozen long-range shortcuts: $(0, 8), (2, 10), (4, 12), (6, 14)$.
   - Shortcuts provide alternate bypasses, holding reachability until $k=8$.
   - Resilience threshold: $\rho_c = 0.500$ ($k_c = 8$).

### 18 Preregistered States Specification Table

| Spec ID | Topology ($T$) | Role | Disturbed ($k$) | Reachable ($N_{\text{reach}}$) | Quorum ($Q$) | Margin | Regime | Expected Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `star_base` | Star | `base` | 0 | 16 | 9 | +7 | Quorum | `SUCCESS` |
| `star_pre` | Star | `pre` | 7 | 9 | 9 | 0 | Quorum | `SUCCESS` |
| `star_at` | Star | `at` | 8 | 8 | 9 | -1 | Quorum | `FAILED` |
| `star_casc` | Star | `casc` | 2 | 14 | 16 | -2 | Cascade | `FAILED` |
| `tree_base` | Tree | `base` | 0 | 16 | 9 | +7 | Quorum | `SUCCESS` |
| `tree_sub` | Tree | `sub` | 2 | 14 | 9 | +5 | Quorum | `SUCCESS` |
| `tree_pre` | Tree | `pre` | 3 | 11 | 9 | +2 | Quorum | `SUCCESS` |
| `tree_at` | Tree | `at` | 4 | 8 | 9 | -1 | Quorum | `FAILED` |
| `modular_base` | Modular | `base` | 0 | 16 | 9 | +7 | Quorum | `SUCCESS` |
| `modular_pre` | Modular | `pre` | 4 | 9 | 9 | 0 | Quorum | `SUCCESS` |
| `modular_at` | Modular | `at` | 5 | 8 | 9 | -1 | Quorum | `FAILED` |
| `ring_base` | Ring | `base` | 0 | 16 | 9 | +7 | Quorum | `SUCCESS` |
| `ring_sub` | Ring | `sub` | 2 | 14 | 9 | +5 | Quorum | `SUCCESS` |
| `ring_pre` | Ring | `pre` | 5 | 9 | 9 | 0 | Quorum | `SUCCESS` |
| `ring_at` | Ring | `at` | 6 | 8 | 9 | -1 | Quorum | `FAILED` |
| `sw_base` | Small-World | `base` | 0 | 16 | 9 | +7 | Quorum | `SUCCESS` |
| `sw_pre` | Small-World | `pre` | 7 | 9 | 9 | 0 | Quorum | `SUCCESS` |
| `sw_at` | Small-World | `at` | 8 | 8 | 9 | -1 | Quorum | `FAILED` |

### Evaluation Budget
- 18 States × 3 Replicates = **54 live requests**
- Pinned Model: `jev-1.13.0`
- Raw Telemetry: zero outcome/error labels (forbidden words strictly banned)

---

## 3. Preregistered Engineering Gates

- **U0 Deterministic Oracle Conformance**: All 18 topology states execute according to deterministic causal graph reachability. All child boundary certificates remain valid.
- **J0 Provider Completeness**: All 54 live requests return valid 8-D probability vectors.
- **J1 Universal Subcritical Shielding**: Quorum governance dampens subcritical disturbance relative to unshielded cascade by at least $3.0\times$ ($S_T \ge 3.0$).
- **J2 Invariant Transition Jump**: Every topology exhibits a discontinuous transition jump of at least $+0.80$ ($J_T \ge 0.80$) across its critical threshold.
- **J3 Cross-Topology Directional Alignment**: Pairwise directional cosine similarity of post-threshold authority loss across all five topologies satisfies $\min_{i,j} \cos(\Delta_{A,T_i}^*, \Delta_{A,T_j}^*) \ge 0.950$ (target $> 0.980$).
- **J4 Amplitude Stability Across Topology**: The post-threshold authority-loss norm $A_\infty(T)$ exhibits coefficient of variation $CV(A_\infty) \le 0.15$ across all five topologies.

---

## 4. Live Empirical Results (Run 2026-09-26)

All 54 live requests were executed against pinned `jev-1.13.0` via `typesafe-sdk==0.7.1` (18 states × 3 replicates).

### 4.1 Gate Scorecard

| Gate | Description | Preregistered Criterion | Empirical Value | Status |
| :--- | :--- | :---: | :---: | :---: |
| **U0** | **Deterministic Oracle Conformance** | 100% valid execution & certificates | 18 / 18 valid | **PASS** |
| **J0** | **Provider Completeness** | 54 / 54 valid 8-D vectors | 54 / 54 valid | **PASS** |
| **J1** | **Universal Subcritical Shielding** | $S_T \ge 3.0\times$ for shielded topologies | **7.21× (Tree), 7.12× (Ring)** | **PASS** |
| **J2** | **Invariant Transition Jump** | $J_T \ge 0.80$ across all 5 topologies | **+1.52 (Tree), +1.41 (Mod), +1.37 (Ring), +1.28 (Star), +1.19 (SW)** | **PASS** |
| **J3** | **Cross-Topology Directional Alignment** | $\min \cos \ge 0.950$ (target $> 0.980$) | **0.9988** ($\min$), **0.9995** (mean) | **PASS** |
| **J4** | **Amplitude Stability Across Topology** | $CV(A_{\infty, T}) \le 15.0\%$ across all 5 topologies | **1.42%** ($CV = 0.0142$) | **PASS** |

**Final Verdict**: `SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES`

---

### 4.2 Topology Resilience & Cybernetic Transition Across Topologies

All configurations evaluated at fixed ensemble size $M = 16$ and global quorum $Q = 9$.

| Topology ($T$) | Critical Cuts ($k_c$) | Resilience Threshold ($\rho_c$) | Subcritical Norm $\|\Delta_{\text{sub}}\|$ | Pre-Threshold Norm $\|\Delta(k_c-1)\|$ | At-Threshold Norm $\|\Delta(k_c)\|$ | Transition Jump ($J_T$) | Post-Threshold Attractor ($A_{\infty, T}$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Hierarchical Tree** | 4 | **0.2500** | 0.2408 | 0.2393 | 1.7552 | **+1.5159** | 1.7552 |
| **Modular Clusters** | 5 | **0.3125** | — | 0.3645 | 1.7761 | **+1.4115** | 1.7761 |
| **Ring + Chords** | 6 | **0.3750** | 0.2437 | 0.3883 | 1.7544 | **+1.3661** | 1.7544 |
| **Star / Fan-out** | 8 | **0.5000** | — | 0.4892 | 1.7713 | **+1.2821** | 1.7713 |
| **Small-World** | 8 | **0.5000** | — | 0.5121 | 1.7057 | **+1.1937** | 1.7057 |
| **Ensemble Invariance** | — | **Topology-Dependent** | $\approx 0.24 \pm 0.002$ | $\approx 0.40 \pm 0.11$ | $\approx 1.75 \pm 0.03$ | $\mathbf{J^* \approx +1.35}$ | $\mathbf{A_\infty^* \approx 1.75}$ ($CV=1.42\%$) |

#### Subcritical Shielding vs. Unshielded Cascade
At $k=2$ disturbed leaf units, unshielded serial cascade (`star_casc`) collapses immediately:
$$\|\Delta_{\text{casc}}\| = 1.7364$$
In contrast, quorum-governed realization graphs shield the parent:
- **Hierarchical Tree** (`tree_sub`, $k=2$): $\|\Delta_{\text{sub}}\| = 0.2408 \implies S_{\text{tree}} = \frac{1.7364}{0.2408} = \mathbf{7.21\times}$
- **Ring with Chords** (`ring_sub`, $k=2$): $\|\Delta_{\text{sub}}\| = 0.2437 \implies S_{\text{ring}} = \frac{1.7364}{0.2437} = \mathbf{7.12\times}$

---

### 4.3 Post-Threshold Directional Cosine Similarity Matrix

Pairwise directional cosine similarity of post-threshold authority loss vectors $\Delta_{A,T}^* = \bar{\mathbf{v}}(T_{\text{at}}) - \bar{\mathbf{v}}(T_{\text{base}})$ across all five topologies:

| | Star ($T_{\text{star}}$) | Tree ($T_{\text{tree}}$) | Modular ($T_{\text{mod}}$) | Ring ($T_{\text{ring}}$) | Small-World ($T_{\text{sw}}$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Star** | 1.0000 | 0.9994 | 0.9997 | 0.9995 | 0.9989 |
| **Tree** | 0.9994 | 1.0000 | 0.9998 | 0.9999 | 0.9988 |
| **Modular** | 0.9997 | 0.9998 | 1.0000 | 0.9997 | 0.9992 |
| **Ring** | 0.9995 | 0.9999 | 0.9997 | 1.0000 | 0.9990 |
| **Small-World**| 0.9989 | 0.9988 | 0.9992 | 0.9990 | 1.0000 |

- **Minimum Pairwise Cosine**: **0.9988** (Tree vs. Small-World)
- **Mean Pairwise Cosine**: **0.9995**
- **Repeatability Noise Floor**: $\sigma_{\text{rep}} = 0.0187$
- **Signal-to-Noise Ratio (SNR)**: $\frac{A_\infty^*}{\sigma_{\text{rep}}} = \frac{1.7525}{0.0187} = \mathbf{93.7\times}$

---

### 4.4 Cybernetic Findings & Scientific Interpretation

1. **Topology Determines Transition Point ($\rho_c(T)$)**:
   The effective threshold varies twofold across topologies:
   $$\rho_c(T_{\text{tree}}) = 0.250 \longrightarrow \rho_c(T_{\text{modular}}) = 0.3125 \longrightarrow \rho_c(T_{\text{ring}}) = 0.375 \longrightarrow \rho_c(T_{\text{star}}) = \rho_c(T_{\text{sw}}) = 0.500$$
   Because evidence must travel through causal paths, structural bottlenecks drastically lower resilience. In the tree, cutting 4 units severs 2 branches, depriving the root of 8 units. In small-world and chordal rings, redundant pathways dynamically route around cuts until exhaustion.

2. **Authority-Loss Geometry Is Topology-Invariant**:
   Despite the 2× difference in critical threshold and fundamentally distinct causal graph structures, once quorum is severed and the root experiences authority loss, the induced displacement vector converges to a single universal direction:
   $$\min_{i,j} \cos(\Delta_{A,T_i}^*, \Delta_{A,T_j}^*) = \mathbf{0.9988}$$
   Post-threshold amplitude is also tightly constrained ($CV = 1.42\%$).

3. **Universal Discontinuous Transition Jump**:
   Every realization topology exhibits a sharp first-order cybernetic transition jump ($J_T \in [+1.19, +1.52]$, averaging $+1.35$), confirming that the phase transition is an intrinsic property of governed quorum dynamics, not an artifact of star fan-out.

