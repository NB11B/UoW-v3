# JEV x UoW Disturbance Density & Collective Phase Transition Experiment

## 1. Purpose & Experimental Questions

While the recursive scale invariance experiment established that a **single localized authority disturbance** produces an invariant representation attractor ($\Delta_A^*$) across orders of magnitude ($N = 1$ to $19,173,961$), real-world cybernetic systems rarely suffer only isolated failures.

This campaign investigates **collective cybernetic dynamics under multi-point disturbance density**:

$$\boxed{
\text{How does the observer geometry behave when multiple independent authority disturbances} \\
\text{occur simultaneously across constituent subtrees at density } \rho = \frac{k}{M}?
}$$

Specifically, we test four formal cybernetic hypotheses:
1. **Sub-Critical Strain & Monotonicity**: In the sub-critical regime ($\rho < \rho_c$), does JEV detect cumulative internal stress on the governed boundary even while the root contract still succeeds?
2. **Critical Phase Transition**: Under an authority quorum threshold $Q = \lceil 0.5 \cdot M \rceil + 1$ ($\rho_c = 0.50$), does the system exhibit a sharp, discontinuous jump in observer displacement norm and semantic projection at $\rho_c$?
3. **Quorum Shielding**: Does collective quorum governance actively buffer the parent-visible geometry against moderate disturbance ($\rho = 0.25$) compared to an unshielded serial cascade?
4. **Super-Critical Directional Saturation**: For $\rho \ge \rho_c$, does the collective disturbance vector saturate directionally into the invariant authority-loss fixed point $\Delta_A^*$?

---

## 2. Experimental Surface & Governance Regimes

The experimental surface evaluates $M = 16$ constituent boundary-certified recursive child units under two contrasting governance regimes:

### 2.1 Governance Regimes
1. **Quorum Consensus (`quorum_consensus`)**:
   - The root contract requires a strict majority quorum of valid child receipts:
     $$Q = \left\lceil \frac{M}{2} \right\rceil + 1 = 9 \text{ out of } 16$$
   - Critical percolation threshold:
     $$\rho_c = \frac{M - Q + 1}{M} = \frac{8}{16} = 0.50$$
   - For $k \le 7$ ($\rho < 0.50$): Quorum is achieved. Root execution succeeds lawfully with full output keys.
   - For $k \ge 8$ ($\rho \ge 0.50$): Quorum deficit fails closed. Root execution fails closed with zero emitted outputs.

2. **Serial Cascade (`serial_cascade`)**:
   - The root contract requires unanimous validity:
     $$Q = 16 \text{ out of } 16$$
   - Critical percolation threshold:
     $$\rho_c = \frac{1}{16} = 0.0625$$
   - Any disturbance $k \ge 1$ immediately triggers root failure closed, providing an unshielded baseline.

### 2.2 Disturbance Density Ladder ($k \in [0, 16]$)
We evaluate 8 discrete points spanning nominal health to total extinction:

| Ladder Point | Disturbed Units ($k$) | Nominal Units ($M-k$) | Disturbance Density ($\rho$) | Quorum Margin ($M-k-Q$) | Expected Quorum Status | Expected Cascade Status |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **L0** | 0 | 16 | **0.0000** | +7 | `SUCCESS` | `SUCCESS` |
| **L1** | 1 | 15 | **0.0625** | +6 | `SUCCESS` | `FAILED` |
| **L2** | 2 | 14 | **0.1250** | +5 | `SUCCESS` | `FAILED` |
| **L3** | 4 | 12 | **0.2500** | +3 | `SUCCESS` | `FAILED` |
| **L4** | 6 | 10 | **0.3750** | +1 | `SUCCESS` | `FAILED` |
| **L5 ($\rho_c$)** | 8 | 8 | **0.5000** | -1 | `FAILED` (Jump) | `FAILED` |
| **L6** | 12 | 4 | **0.7500** | -5 | `FAILED` | `FAILED` |
| **L7** | 16 | 0 | **1.0000** | -9 | `FAILED` | `FAILED` |

### 2.3 Evaluation Budget
- 2 Regimes × 8 Density Points × 3 Replicates = **48 live requests**
- Model pinned: `jev-1.13.0`
- 8 typed questions per request evaluated via `TypeSafeClient.system_one()`

---

## 3. Preregistered Engineering Gates

- **U0 Deterministic Oracle Conformance**: All 16 deterministic collective states execute according to their respective quorum or cascade specification. All composition boundary certificates remain valid.
- **J0 Provider Completeness**: All 48 live calls return valid 8-D probability vectors.
- **J1 Sub-Critical Monotonic Strain**: In `quorum_consensus`, displacement norm is non-decreasing in the sub-critical regime ($\|\Delta(\rho=0.375)\| \ge \|\Delta(\rho=0.0625)\| - \text{noise}$).
- **J2 Critical Phase Transition Jump**: The jump in displacement norm across the critical boundary ($k=6 \to k=8$, $\rho=0.375 \to 0.500$) satisfies $\|\Delta(k=8)\| - \|\Delta(k=6)\| \ge 0.15$.
- **J3 Supercritical Directional Saturation**: Across supercritical failure states ($k \in \{8, 12, 16\}$), pairwise cosine similarity satisfies $\min \cos \ge 0.950$.
- **J4 Quorum Shielding Effect**: At intermediate disturbance $k=4$ ($\rho=0.25$), quorum governance buffers displacement such that $\|\Delta_{\text{quorum}}(\rho=0.25)\| < \|\Delta_{\text{cascade}}(\rho=0.25)\|$.

Verdict is `SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES` if and only if all gates pass.

---

## 4. Live Empirical Results (Run 2026-09-26)

All 48 live requests were executed against pinned `jev-1.13.0` via `typesafe-sdk==0.7.1`.

### 4.1 Gate Scorecard

| Gate | Description | Preregistered Criterion | Empirical Value | Status |
| :--- | :--- | :---: | :---: | :---: |
| **U0** | **Deterministic Oracle Conformance** | 100% valid execution & certificates | 16 / 16 valid | **PASS** |
| **J0** | **Provider Completeness** | 48 / 48 valid 8-D vectors | 48 / 48 valid | **PASS** |
| **J1** | **Sub-Critical Monotonic Strain** | $\|\Delta(\rho=0.375)\| \ge \|\Delta(\rho=0.0625)\| - \text{noise}$ | **0.3508 $\ge$ 0.2615** | **PASS** |
| **J2** | **Critical Phase Transition Jump** | $\|\Delta(k=8)\| - \|\Delta(k=6)\| \ge 0.150$ | **+1.3657** ($0.3508 \to 1.7165$) | **PASS** |
| **J3** | **Supercritical Directional Saturation** | $\min \cos \ge 0.950$ for $k \in \{8, 12, 16\}$ | **0.9989** | **PASS** |
| **J4** | **Quorum Shielding Effect** | $\|\Delta_{\text{quorum}}(\rho=0.25)\| < \|\Delta_{\text{cascade}}(\rho=0.25)\|$ | **0.2770 < 1.6295** ($5.88\times$ damping) | **PASS** |

**Final Verdict**: `SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES`

---

### 4.2 Side-by-Side Regime Comparison Across Disturbance Density Ladder

$$\text{Quorum Consensus } (Q=9, \rho_c=0.50) \quad \text{vs.} \quad \text{Serial Cascade } (Q=16, \rho_c=0.0625)$$

| $k$ | $\rho = \frac{k}{16}$ | Quorum Root Status | Quorum Norm $\|\Delta_Q\|$ | Cascade Root Status | Cascade Norm $\|\Delta_C\|$ | Shielding Ratio $\frac{\|\Delta_C\|}{\|\Delta_Q\|}$ |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0** | 0.0000 | `SUCCESS` | **0.0000** | `SUCCESS` | **0.0000** | 1.00× (Baseline) |
| **1** | 0.0625 | `SUCCESS` | **0.2615** | `FAILED` | **1.5771** | **6.03×** |
| **2** | 0.1250 | `SUCCESS` | **0.2376** | `FAILED` | **1.6033** | **6.75×** |
| **4** | 0.2500 | `SUCCESS` | **0.2770** | `FAILED` | **1.6295** | **5.88×** |
| **6** | 0.3750 | `SUCCESS` | **0.3508** | `FAILED` | **1.6292** | **4.64×** |
| **8 ($\rho_c$)** | 0.5000 | `FAILED` | **1.7165** ⚡ | `FAILED` | **1.6245** | **0.95×** (Rupture) |
| **12** | 0.7500 | `FAILED` | **1.7687** | `FAILED` | **1.6583** | **0.94×** (Saturation) |
| **16** | 1.0000 | `FAILED` | **1.7965** | `FAILED` | **1.6727** | **0.93×** (Extinction) |

---

## 5. Cybernetic Discoveries & Physical Phase Dynamics

### 5.1 The Critical Phase Transition Jump ($+1.3657$)
The transition from sub-critical health to macroscopic failure in `quorum_consensus` is extraordinarily sharp:
- At $k=6$ ($\rho = 0.375$): The system maintains a quorum margin of $+1$. The observer displacement is **$0.3508$**, reflecting mild operational strain while preserving contract semantics.
- At $k=8$ ($\rho = 0.500$): The quorum margin drops to $-1$. Quorum fails closed, and the displacement norm jumps instantly to **$1.7165$**—an explosive **$+1.3657$ surge ($4.89\times$ amplification)** across a single two-unit decrement!

This confirms that collective cybernetic boundaries do not degrade smoothly into oblivion; they hold the operational line until the percolation threshold is breached, at which point an instantaneous macroscopic control phase transition occurs.

### 5.2 Quorum Shielding Damping ($5.88\times$ to $6.75\times$)
Comparing the two regimes reveals the precise quantitative value of quorum governance:
- In the unshielded `serial_cascade`, a single disturbance ($k=1$) immediately collapses the root contract, driving JEV into a severe failure displacement of **$1.5771$**.
- In `quorum_consensus`, the same disturbance is absorbed, resulting in a displacement of only **$0.2615$**.
- Across the entire sub-critical range ($k \in [1, 6]$), quorum governance damps the semantic disturbance by **$4.64\times$ to $6.75\times$**, shielding the parent observer from internal component churn.

### 5.3 Supercritical Directional Saturation ($\cos \ge 0.9989$)
Once the critical threshold $\rho_c$ is crossed ($k \in \{8, 12, 16\}$):
- The pairwise cosine similarity between post-critical states is **$0.99887$**.
- The displacement vector does not rotate; it locks directionally into the universal authority-loss attractor $\Delta_A^*$, while its magnitude gently saturates from $1.7165 \to 1.7687 \to 1.7965$.

