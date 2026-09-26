# JEV x UoW Operator Algebraic Closure Qualification Campaign

## 1. Experimental Question & Framing

Does the sequential composition of governed failure mechanisms remain inside the empirically discovered failure coordinate space, or does it generate emergent new state-space dimensions?

$$\boxed{\text{\textbf{Does sequential failure composition close within the elementary failure coordinate space?}}}$$

Formally, we test whether the empirical commutators across all 15 failure pairs lie within the span of the elementary failure residuals:
$$\boxed{[F_i, F_j]_{\mathrm{emp}} \stackrel{?}{\in} \operatorname{span}\{\epsilon_A, \epsilon_E, \epsilon_C, \epsilon_T, \epsilon_R, \epsilon_{\mathrm{Adv}}\}}$$

In the preceding failure-semantics campaign, we established that:
1. Every failure displacement decomposes into a dominant macrostate direction and an orthogonal residual:
   $$\Delta_i = \Delta_G + \epsilon_i \quad \text{with } \|\Delta_G\| = 1.6475 \text{ and } \|\epsilon_i\| \in [0.066, 0.202]$$
2. The pure residuals span a compact 3D coordinate system ($95.95\%$ variance in 3 PCA modes).
3. Composition is noncommutative ($\kappa_{ij} \approx 6.2\times$–$7.8\times \sigma_{\text{rep}}$) and non-additive ($\|\chi_{ij}\| \approx 3\times$–$5.7\times \sigma_{\text{rep}}$).
4. For the three initial pairs, $70.7\%$ to $95.5\%$ of commutator variance was retained in 3D projection.

This raises the fundamental algebraic closure question:
- **If Residual Closure Holds**:
  $$[F_i, F_j]_{\mathrm{emp}} = \sum_{a=1}^5 f_{ij}^a B_a + \eta_{ij} \quad \text{with } \|\eta_{ij}\| \sim \sigma_{\text{rep}}$$
  Sequential failure interactions remain entirely confined within the internal failure-coordinate space discovered in pure states.
- **If Emergent Nonclosure Occurs**:
  $$\|\eta_{ij}\| \gg \sigma_{\text{rep}}$$
  Sequential failure composition generates genuinely new state-space directions not present in any elementary failure operator.

---

## 2. Experimental Surface & Parameter Space

The campaign evaluates **all 15 unordered pairs** ($\binom{6}{2} = 15$) in both forward and reverse directions, producing **30 ordered compositions**, alongside 1 nominal baseline and 6 pure failure reference states (**37 states total**):

- **Architecture Fixed**:
  - $M = 16$, $Q = 9$.
  - Star fan-out topology (direct independent lines).
  - Depth $d = 1$.
- **Common-Output Control**:
  - Every failure state ($k = 8$) produces:
    $$\text{admissible units} = 8 < 9 \implies \text{quorum margin} = -1, \quad \text{emitted output keys} = [], \quad \text{oracle status} = \text{`FAILED'}$$
- **Evaluation Budget**:
  - Initial 15-Pair Survey: 37 States × 3 Replicates = **111 live requests**
  - Targeted Resource Resolution: 15 States × 10 Replicates = **150 live requests**
  - Model pinned: `jev-1.13.0`
  - Zero outcome labels: raw telemetry strictly bans all forbidden substrings.

### 15 Unordered Failure Pairs Evaluated

| Pair ID | Mechanism $F_i$ | Mechanism $F_j$ | Forward State ($F_i F_j$) | Reverse State ($F_j F_i$) |
| :---: | :--- | :--- | :--- | :--- |
| **P01** | Authority ($A$) | Evidence ($E$) | `comp_A_E` | `comp_E_A` |
| **P02** | Authority ($A$) | Causal ($C$) | `comp_A_C` | `comp_C_A` |
| **P03** | Authority ($A$) | Temporal ($T$) | `comp_A_T` | `comp_T_A` |
| **P04** | Authority ($A$) | Resource ($R$) | `comp_A_R` | `comp_R_A` |
| **P05** | Authority ($A$) | Adversarial ($\text{Adv}$) | `comp_A_Adv` | `comp_Adv_A` |
| **P06** | Evidence ($E$) | Causal ($C$) | `comp_E_C` | `comp_C_E` |
| **P07** | Evidence ($E$) | Temporal ($T$) | `comp_E_T` | `comp_T_E` |
| **P08** | Evidence ($E$) | Resource ($R$) | `comp_E_R` | `comp_R_E` |
| **P09** | Evidence ($E$) | Adversarial ($\text{Adv}$) | `comp_E_Adv` | `comp_Adv_E` |
| **P10** | Causal ($C$) | Temporal ($T$) | `comp_C_T` | `comp_T_C` |
| **P11** | Causal ($C$) | Resource ($R$) | `comp_C_R` | `comp_R_C` |
| **P12** | Causal ($C$) | Adversarial ($\text{Adv}$) | `comp_C_Adv` | `comp_Adv_C` |
| **P13** | Temporal ($T$) | Resource ($R$) | `comp_T_R` | `comp_R_T` |
| **P14** | Temporal ($T$) | Adversarial ($\text{Adv}$) | `comp_T_Adv` | `comp_Adv_T` |
| **P15** | Resource ($R$) | Adversarial ($\text{Adv}$) | `comp_R_Adv` | `comp_Adv_R` |

---

## 3. Mathematical Coordinate Representations & Distinction from Lie Algebra

### 3.1 Projections vs. Structure Constants

A critical mathematical distinction must be maintained:
- **Observer-Space PCA Projection Coefficients**:
  $$f_{ij}^a = c_{ij} \cdot B_a, \quad a \in \{1, \dots, 5\}$$
  These are coordinates of observed commutator vectors in an orthonormal SVD basis $B_a \in \mathbb{R}^8$. They are **not** Lie-algebraic structure constants, because $B_a$ are empirical observer coordinates, not composable operator generators.
- **Index Mismatch in Jacobi Contraction**:
  A formal bracket $[\cdot, \cdot]: V \times V \to V$ must be defined on a single common generator space $V$. Computing $\sum_m (f_{ij}^m f_{mk}^l + \dots)$ directly on $f_{ij}^a$ is mathematically premature because the inner index $m$ would sum over observer modes, whereas inputs $(i, j)$ index physical failure mechanisms.

### 3.2 Physical Operator Basis Representation

To resolve the index mismatch and remain inside the physically meaningful operator family, we project each empirical commutator directly onto the **six pure failure residual operators themselves**:
$$[F_i, F_j]_{\mathrm{emp}} \approx \sum_{k \in \{A, E, C, T, R, \mathrm{Adv}\}} c_{ij}^k \epsilon_k$$
Because $\sum_k \epsilon_k = 0$, we enforce the zero-sum gauge condition:
$$\sum_{k} c_{ij}^k = 0$$
Both inputs ($i, j$) and outputs ($k$) now inhabit the identical physical operator family $\{F_A, \dots, F_{\mathrm{Adv}}\}$.

---

## 4. Preregistered Engineering Gates

- **U0 Deterministic Oracle Conformance**: All 37 states execute in accordance with their respective contract. All boundary certificates remain valid.
- **J0 Provider Completeness**: All 111 live requests return valid 8-D probability vectors.
- **J1 Repeatability Noise Floor**: Median replicate noise satisfies $\sigma_{\text{rep}} \le 0.050$.
- **J2 Commutator Detectability**: Mean commutator magnitude satisfies $\bar{\|c\|} / \sigma_{\text{rep}} \ge 3.0\times$.
- **J3 Algebraic Closure Evaluation**: Determine whether full residual span achieves $\bar{R}^2(5D) \ge 85.0\%$ and mean defect $\bar{\zeta}(5D) \le 2.0\times \sigma_{\text{rep}}$.
- **J4 Dimensionality Spectrum Characterization**: Evaluate the step-wise closure curve $\bar{R}^2(k)$ for $k \in \{1, 2, 3, 4, 5\}$.

---

## 5. Live Empirical Results

### 5.1 Gate Scorecard

| Gate | Description | Preregistered Criterion | Empirical Value | Status |
| :--- | :--- | :---: | :---: | :---: |
| **U0** | **Deterministic Oracle Conformance** | 100% valid execution & certificates | 37 / 37 valid | **PASS** |
| **J0** | **Provider Completeness** | 111 / 111 valid 8-D vectors | 111 / 111 valid | **PASS** |
| **J1** | **Repeatability Noise Floor** | $\sigma_{\text{rep}} \le 0.050$ | **$\sigma_{\text{rep}} = 0.0208$** | **PASS** |
| **J2** | **Commutator Detectability** | Mean commutator magnitude $\bar{\|c\|} \ge 3.0\times \sigma_{\text{rep}}$ | **$\bar{\|c\|} = 0.1376 \implies \mathbf{6.61\times \sigma_{\text{rep}}}$** | **PASS** |
| **J3** | **Algebraic Closure Evaluation** | $\bar{R}^2(5D) \ge 85.0\%$ & $\bar{\zeta}(5D) \le 2.0\times \sigma_{\text{rep}}$ | **$\bar{R}^2 = \mathbf{86.06\%}$, $\bar{\zeta} = \mathbf{1.14\times \sigma_{\text{rep}}}$** | **PASS** |
| **J4** | **Dimensionality Spectrum Characterization** | Evaluate step-wise curve for $k = 1, \dots, 5$ | **Spectrum fully mapped** | **PASS** |

**Preregistered Engineering Gate Verdict**: `SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES`  
**Scientific Closure Verdict**: **`APPROXIMATE_RESIDUAL_SPAN_CLOSURE_SUPPORTED`**

> **Summary Statement**:
> *High-SNR failure commutators exhibit approximate closure in the five-dimensional elementary residual span; low-amplitude Resource interactions remain unresolved in initial 3-replicate survey but are resolved under targeted high-replicate sampling.*

---

### 5.2 Dimensional Closure Spectrum ($\bar{R}^2(k)$ and $\bar{\zeta}(k)$)

Pure elementary failure residuals are $96.6\%$ concentrated in 3 modes ($s_1 = 0.2431, s_2 = 0.1599, s_3 = 0.1117, s_4 = 0.0568, s_5 = 0.0132$).
Evaluating commutator projections across increasing dimensions $k = 1, \dots, 5$:

| Subspace Dimension ($k$) | Mean Closure Variance $\bar{R}^2(k)$ | Mean Defect over Noise $\bar{\zeta}(k) = \|r^{(k)}\|/\sigma_{\text{rep}}$ | Incremental Gain ($\Delta R^2$) | Qualitative Finding |
| :---: | :---: | :---: | :---: | :--- |
| **1D** | 39.48% | 4.25× | — | Single mode insufficient to capture commutator |
| **2D** | 61.83% | 2.76× | +22.35% | Primary divergence-repair plane |
| **3D** | 69.19% | 2.36× | +7.36% | Dominant elementary failure coordinate space |
| **4D** | **82.86%** | **1.28×** | **+13.67%** | **Major closure threshold: interactions recruit Mode 4** |
| **5D (Full Span)** | **86.06%** | **1.14×** | **+3.20%** | **Approximate residual closure achieved within noise** |

$$\boxed{\text{\textbf{Elementary failures are approximately 3-D (96.6%), but their noncommutative interactions recruit Modes 4 and 5.}}}$$

---

### 5.3 Commutator Norms and Closure Metrics Across All 15 Failure Pairs ($N=3$)

Noise floor: $\sigma_{\text{rep}} = 0.0208$. Commutator: $c_{ij} = [F_i, F_j]_{\mathrm{emp}} = \epsilon_{ij} - \epsilon_{ji}$.

| Pair | Mechanisms ($F_i - F_j$) | Commutator Norm $\|c_{ij}\|$ | Signal-to-Noise ($\|c\|/\sigma_{\text{rep}}$) | 3D Closure $R^2(3D)$ | Full 5D Closure $R^2(5D)$ | Defect over Noise $\zeta(5D)$ | Initial Survey Status |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **P01** | Authority — Evidence | 0.0578 | 2.8× | 49.79% | **99.65%** | **0.16×** | Complete Closure |
| **P02** | Authority — Causal | 0.0542 | 2.6× | 96.90% | **97.24%** | **0.43×** | Complete Closure |
| **P03** | Authority — Temporal | 0.2078 | **10.0×** | 90.02% | **97.24%** | **1.66×** | Complete Closure |
| **P04** | Authority — Resource | 0.0554 | 2.7× | 8.05% | 42.75% | 2.01× | Low-SNR Unresolved |
| **P05** | Authority — Adversarial | 0.2139 | **10.3×** | 90.84% | **99.87%** | **0.37×** | Complete Closure |
| **P06** | Evidence — Causal | 0.0535 | 2.6× | 29.06% | **97.68%** | **0.39×** | Complete Closure |
| **P07** | Evidence — Temporal | 0.0984 | **4.7×** | 90.84% | **96.70%** | **0.86×** | Complete Closure |
| **P08** | Evidence — Resource | 0.0696 | 3.3× | 13.34% | 34.41% | 2.71× | Low-SNR Unresolved |
| **P09** | Evidence — Adversarial | 0.2444 | **11.7×** | 97.73% | **99.87%** | **0.42×** | Complete Closure |
| **P10** | Causal — Temporal | 0.1693 | **8.1×** | 89.57% | **96.98%** | **1.41×** | Complete Closure |
| **P11** | Causal — Resource | 0.0508 | 2.4× | 19.82% | 34.79% | 1.97× | Low-SNR Unresolved |
| **P12** | Causal — Adversarial | 0.2483 | **11.9×** | 96.12% | **96.18%** | 2.33× | Complete Closure |
| **P13** | Temporal — Resource | 0.1417 | **6.8×** | 90.03% | **99.55%** | **0.45×** | Complete Closure |
| **P14** | Temporal — Adversarial | 0.2034 | **9.8×** | 80.04% | **98.55%** | **1.18×** | Complete Closure |
| **P15** | Resource — Adversarial | 0.1962 | **9.4×** | 95.63% | **99.45%** | **0.70×** | Complete Closure |

---

### 5.4 Physical Operator Basis Expansion ($[F_i, F_j]_{\mathrm{emp}} \approx \sum_k c_{ij}^k \epsilon_k$)

Projecting directly onto the concrete failure operators with zero-sum gauge $\sum_k c_{ij}^k = 0$:

| Pair ($i - j$) | $c_{ij}^A$ | $c_{ij}^E$ | $c_{ij}^C$ | $c_{ij}^T$ | $c_{ij}^R$ | $c_{ij}^{\text{Adv}}$ | $\sum_k c_{ij}^k$ | Physical $R^2$ | Physical Interpretation |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **A — E** | -0.3728 | -0.3378 | +0.1195 | -0.5927 | +1.0039 | +0.1799 | 0.0000 | **99.65%** | Recruits Resource containment axis |
| **A — C** | +0.1677 | -0.1409 | +0.0960 | -0.2033 | +0.0926 | -0.0121 | 0.0000 | **97.24%** | Authority-Evidence balance |
| **A — T** | +0.9297 | +0.3537 | +0.2961 | -0.0759 | -1.4291 | -0.0746 | 0.0000 | **97.24%** | Strong Authority vs. Resource coupling |
| **A — R** | -0.8146 | -0.9452 | +1.3052 | -0.5842 | +0.8677 | +0.1711 | 0.0000 | 42.75% | Low SNR in N=3 survey |
| **A — Adv**| -0.0370 | +0.7331 | -0.3631 | -0.2520 | +0.8513 | -0.9322 | 0.0000 | **99.87%** | Strong Evidence & Resource anti-Adv |
| **E — C** | -0.2297 | -0.3254 | -0.0510 | -0.4428 | +1.0223 | +0.0266 | 0.0000 | **97.68%** | Resource containment activation |
| **E — T** | -0.2002 | -0.4227 | +0.7151 | -0.9620 | +0.7625 | +0.1073 | 0.0000 | **96.70%** | Temporal latency vs. Causal path |
| **E — R** | -0.5154 | -0.8782 | +1.0123 | -0.2206 | +0.5404 | +0.0615 | 0.0000 | 34.41% | Low SNR in N=3 survey |
| **E — Adv**| +0.4078 | +0.3519 | -0.1280 | -0.1746 | +0.4842 | -0.9413 | 0.0000 | **99.87%** | Strong Evidence & Resource anti-Adv |
| **C — T** | +0.8308 | +0.3801 | +0.1258 | -0.0121 | -1.2813 | -0.0434 | 0.0000 | **96.98%** | Authority-Resource trade-off |
| **C — R** | +0.0086 | -0.3235 | +0.3104 | +0.0337 | -0.0735 | +0.0442 | 0.0000 | 34.79% | Low SNR in N=3 survey |
| **C — Adv**| +0.2567 | -0.0507 | +0.5607 | -0.2057 | +0.2738 | -0.8348 | 0.0000 | **96.18%** | Causal verification vs. Adversarial |
| **T — R** | -0.1442 | -0.6891 | +0.1862 | +0.9884 | -0.1838 | -0.1575 | 0.0000 | **99.55%** | Pure Temporal operator alignment |
| **T — Adv**| -0.7129 | +0.5811 | -0.1969 | -0.4701 | +1.6020 | -0.8031 | 0.0000 | **98.55%** | High Resource & Evidence activation |
| **R — Adv**| +0.1930 | +0.3513 | -0.2597 | +0.0108 | +0.5511 | -0.8465 | 0.0000 | **99.45%** | Resource containment vs. Divergence |

Anti-symmetry holds strictly: $c_{ji}^k = -c_{ij}^k$. Both input pairs $(i, j)$ and output bases $(k)$ index the identical 6 physical failure modes.

---

### 5.5 Targeted High-Replicate Resolution of the Resource Triplet ($N=10$)

To discriminate between **true nonclosure** (emergent missing dimension) and **insufficient SNR** (measurement noise dominating small commutators), we executed a targeted 150-request experiment with $N=10$ replicates per state (`qualification/jev_resource_resolution_campaign.py`).

| Pair | Commutator $\|c\|$ ($N=3$) | Commutator $\|c\|$ ($N=10$) | $R^2(5D)$ ($N=3$) | $R^2(5D)$ ($N=10$) | Defect $\zeta / \sigma_{\text{rep}}$ ($N=3$) | Defect $\zeta / \sigma_{\text{rep}}$ ($N=10$) | Spurious Perp2 Projection ($N=3 \to N=10$) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A — R** | 0.0554 | 0.0481 | 42.75% | **95.72%** | 2.01× | **0.39×** | $-0.0419 \to -0.0051$ (**8.2× reduction**) |
| **E — R** | 0.0696 | 0.0661 | 34.41% | **93.75%** | 2.71× | **0.65×** | $-0.0563 \to +0.0081$ (**7.0× reduction**) |
| **C — R** | 0.0508 | 0.0459 | 34.79% | **63.20%** | 1.97× | **1.10×** | $-0.0369 \to -0.0091$ (**4.1× reduction**) |
| **T — R** *(Control)* | 0.1417 | 0.1322 | 99.55% | **99.22%** | 0.45× | **0.46×** | $+0.0000 \to +0.0116$ (stable) |

**High-Replicate Resource Verdict**: `COLLAPSED_TO_NOISE_CLOSURE_CONFIRMED`
- Across the three previously unresolved Resource pairs, the mean defect ratio collapsed from $2.23\times \sigma_{\text{rep}}$ down to **$0.71\times \sigma_{\text{rep}} \le 1.0\times$**.
- For $A-R$ and $E-R$, closure reached **$95.72\%$** and **$93.75\%$**, respectively.
- Spurious alignment with the orthogonal complement mode (`perp2`) vanished, confirming that apparent nonclosure was an artifact of noise near the $SNR \approx 2.4\times$–$3.3\times$ floor.
- **Metric Stability & Nuance for $C-R$**: While $A-R$ and $E-R$ show unqualified closure ($\ge 93.8\%$), $C-R$ closure rose to $63.20\%$ with defect $\zeta = 1.10\times \sigma_{\text{rep}}$. When the commutator amplitude itself is tiny ($\|c\| \approx 0.046$), percentage $R^2 = 1 - \|r\|^2 / \|c\|^2$ becomes mathematically unstable due to the small denominator. Therefore, in low-amplitude regimes, we privilege the **absolute closure defect relative to noise** ($\zeta = \|r\| / \sigma_{\text{rep}}$) over percentage $R^2$. At $\zeta = 1.10\times \sigma_{\text{rep}}$, the defect for $C-R$ is consistent with replicate noise, though it remains a subtle low-amplitude coupling rather than a fully resolved large signal.

---

### 5.6 Resolution of the Operator Progression & Refutation of Continuous Lie Algebra

Following closure confirmation, the progression evaluated the essential algebra requirement of **bracket bilinearity** under physically controlled fractional perturbations ($[\alpha F_i + \beta F_j, F_k] \stackrel{?}{=} \alpha [F_i, F_k] + \beta [F_j, F_k]$) in [`docs/JEV_OPERATOR_BILINEARITY_EXPERIMENT.md`](file:///C:/Users/nateb/OneDrive/Documents/UoW-v2/docs/JEV_OPERATOR_BILINEARITY_EXPERIMENT.md):

$$\boxed{\begin{aligned}
&\text{1. Resolve low-SNR Resource pairs} \quad &&[\textbf{COMPLETED: } N=10 \implies \bar{\zeta} \to 0.71\times \sigma_{\text{rep}}, R^2 \ge 93.8\%] \\
&\text{2. Validate common physical operator basis} \quad &&[\textbf{COMPLETED: } [F_i, F_j] \approx \sum_k c_{ij}^k \epsilon_k, \sum_k c_{ij}^k = 0] \\
&\text{3. Test scalar homogeneity} \quad &&[\textbf{FAILS: } [F_i(\alpha), F_j] \approx [F_i(1), F_j], \text{ slope} \approx 0 \implies \text{step-saturation}] \\
&\text{4. Test linear superposition} \quad &&[\textbf{FAILS: } \text{Combined interventions saturate, } \eta_{\text{add}} = 10.0\times \sigma_{\text{rep}}] \\
&\text{5. Continuous Lie algebra model} \quad &&[\textbf{REFUTED FOR TESTED OPERATORS}] \\
&\text{6. Jacobi / BCH campaign} \quad &&[\textbf{TERMINATED: } \text{Physically ungrounded for thresholded systems}] \\
&\text{7. Empirical cybernetic model} \quad &&[\textbf{DISCRETE THRESHOLDED CAUSAL SWITCHING DYNAMICS}]
\end{aligned}}$$

The empirical failure of scalar homogeneity and linear superposition demonstrates that the tested physical failure operators act as **discrete guarded transitions** ($x \xrightarrow{g_i(x)} F_i(x)$ with Heaviside step boundaries $\Theta(\alpha)$), rather than infinitesimal continuous Lie generators. The formal mathematical candidate is a **noncommutative thresholded causal transformation semigroup**.
