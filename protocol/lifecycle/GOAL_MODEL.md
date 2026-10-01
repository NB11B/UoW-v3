# Architectural Specification: Goal Model & Optimization Semantics

## 1. Formal Invariants of the Goal Model

The UoW v2.0 Goal Model formalizes how objectives are defined, scheduled, prioritized, and evaluated across operational states.

$$\boxed{
\begin{aligned}
\text{Constraints} &\neq \text{Objectives}\\
G_t &= f(S_t, P)\\
G_t &\subseteq P_{\mathrm{authorized}}\\
\pi_t &= P_\theta(S_t, G_t, C_t, A_t)
\end{aligned}
}$$

---

## 2. Invariant vs Objective Separation: $\text{Constraints} \neq \text{Objectives}$

A common failure mode in AI and distributed systems is treating safety constraints as terms in a weighted cost function:
$$\text{Flawed Cost Function: } \mathcal{L}(\pi) = w_1 \cdot \text{Cost} + w_2 \cdot \text{Throughput} - \lambda \cdot \mathbf{1}_{[\text{Hazard}]}$$

In any weighted scalarization, if $w_2 \cdot \text{Throughput}$ is sufficiently large, the optimization policy will deliberately accept the penalty $\lambda$ and breach the constraint.

**UoW v2.0 strictly rejects weighted constraint relaxation.**

### Formal Definition:
* Let $\mathcal{S}$ be the set of all world states.
* Let $\mathcal{I} = \{i_1, i_2, \dots, i_m\}$ be the set of hard invariants defined in `SystemDesignProfile.invariants`.
* The feasible domain $\Omega$ is defined as:
  $$\Omega = \{ s \in \mathcal{S} \mid \forall k \in \{1, \dots, m\}, \; i_k(s) = \text{True} \}$$
* Objectives $\mathcal{G} = \{g_1, g_2, \dots, g_n\}$ are optimization targets evaluated **only on states within $\Omega$**:
  $$J_k(s): \Omega \longrightarrow \mathbb{R}$$
* Any candidate proposal $\pi_t$ that transitions the world to $S_{t+1} \notin \Omega$ is rejected unconditionally by the Authority Plane with error code `ERR_INVARIANT_VIOLATION`, regardless of the value $\sum_k J_k(S_{t+1})$.

---

## 3. Dynamic Goal Selection: $G_t = f(S_t, P)$

Active goals are dynamic and context-dependent. They are computed by a deterministic evaluation function over the current certified world state $S_t$ and active profile $P$:

$$G_t = f(S_t, P)$$

### Goal Resolution Algorithm:
1. **Operating Mode Resolution**: Determine current mode $M_t = \text{ModeEngine}(S_t, P)$.
2. **Mode-Allocated Goals**: Select candidate goals $\mathcal{G}_{\text{mode}} = P.\text{goals\_by\_mode}[M_t]$.
3. **Precondition Filtering**: For each goal $g \in \mathcal{G}_{\text{mode}}$, evaluate whether its activation preconditions in $S_t$ are satisfied:
   $$G_t = \{ g \in \mathcal{G}_{\text{mode}} \mid \text{EvalPreconditions}(g, S_t) = \text{True} \}$$

### Authorization Bounding: $G_t \subseteq P_{\mathrm{authorized}}$
No agent, planner, or external actor may propose or activate a goal that is not explicitly declared and certified within the active `SystemDesignProfile`.
$$\forall g \in G_t \implies g \in P.\text{goals}$$
Any proposal containing unauthorized goal parameters or attempting to introduce novel goal definitions triggers `ERR_UNAUTHORIZED_GOAL`.

---

## 4. Priority Dominance & Conflict Resolution

When multiple objectives compete for finite resources (e.g. latency vs energy efficiency), conflict resolution is strictly governed by **Lexicographic Dominance**:

$$g_a \succ g_b \iff \text{priority\_rank}(g_a) < \text{priority\_rank}(g_b)$$

### Lexicographic Selection Rule:
Given a set of candidate proposals $\Pi = \{\pi_1, \pi_2, \dots, \pi_k\}$ that all preserve invariants ($\forall \pi \in \Pi, \pi(S_t) \in \Omega$):
1. Evaluate highest-priority goal $g_1$. Select subset $\Pi_1 \subseteq \Pi$ that maximizes $J_1(\pi(S_t))$ within tolerance $\epsilon_1$.
2. If $|\Pi_1| > 1$, evaluate $g_2$ on $\Pi_1$. Select $\Pi_2 \subseteq \Pi_1$ maximizing $J_2$.
3. Repeat recursively for subsequent priority ranks.
4. If a tie remains after all goals are evaluated, select the proposal with the minimum state deviation (least action principle).

---

## 5. Candidate Action Generation: $\pi_t = P_\theta(S_t, G_t, C_t, A_t)$

Autonomous agents generate candidate action proposals $\pi_t$ according to their internal reasoning or neural policy $P_\theta$. The proposal is explicitly conditioned on:
* $S_t$: Current world state (verified attributes and recent evidence).
* $G_t$: Currently active goals derived from the profile.
* $C_t$: Hard invariant boundary constraints ($\Omega$).
* $A_t$: Authorized action space for the active operating mode.

$$\pi_t = (\text{agent\_id}, H_{\text{pre}}, \text{target\_uow}, \text{arguments}, \text{reasoning\_trace})$$

**Zero-Authority Guarantee**:
The agent submits $\pi_t$ to the kernel queue. The kernel evaluates:
1. Freshness: $H_{\text{pre}} == S_t.\text{hash}$
2. Authorization: $\text{target\_uow} \in A_t$
3. Invariant Preservation: $\text{DeterministicMutate}(\pi_t, S_t) \in \Omega$
4. Contract Guards: $\text{Guard}(\pi_t.\text{arguments}, S_t) == \text{True}$

Only proposals satisfying all 4 checks are certified into `CertificateResult` and committed to the ledger.
