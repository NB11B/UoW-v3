# Substrate Specification: Temporal Semantics

## 1. Executive Axiom

$$\boxed{\text{Event Order} \neq \text{Wall-Clock Order}}$$

Relying purely on wall-clock time (NTP) in distributed, embedded, or multi-agent systems is catastrophic. Clock skew, leap seconds, VM pauses, and relativistic network latency mean that timestamp $T_A < T_B$ does **not** prove that event $A$ caused or preceded event $B$.

UoW v2.0 strictly decouples physical wall-clock time from causal ordering, and establishes an explicit **eight-dimensional temporal coordinate system**.

---

## 2. The Eight Temporal Coordinates

$$\begin{array}{|l|l|l|}
\hline
\textbf{Coordinate} & \textbf{Clock Source} & \textbf{Architectural Role} \\
\hline
\textbf{1. Observed Time} & \text{Sensor Hardware Clock} & \text{When physical phenomenon was sampled} \\
\textbf{2. Received Time} & \text{Ingress Gateway System Clock} & \text{When packet crossed system network boundary} \\
\textbf{3. Logical Time} & \textbf{Causal Epoch \& OCC Sequence} & \textbf{Authoritative causality and state ordering} \\
\textbf{4. Execution Deadline} & \text{Monotonic Relative Timer} & \text{Hard limit on execution duration} \\
\textbf{5. Lease Expiry} & \text{Monotonic Timer} & \text{When resource or authority reservation lapses} \\
\textbf{6. Retry Interval} & \text{Exponential Backoff Policy} & \text{Delay before resubmitting rejected candidate} \\
\textbf{7. Scheduled Time} & \text{Cron / Future Epoch} & \text{Deferred execution trigger} \\
\textbf{8. Validity Interval} & \text{Interval } [t_{\text{start}}, t_{\text{end}}] & \text{Legal validity window for claims and certificates} \\
\hline
\end{array}$$

---

## 3. Causal Ordering & OCC Monotonicity

1. **State Ordering is Governed Exclusively by Logical Sequence**:
   $$\text{Predecessor State } S_t \prec S_{t+1} \iff \text{sequence}(S_{t+1}) = \text{sequence}(S_t) + 1$$
   No wall-clock timestamp can alter the topological sequence of state transitions.

2. **Causal Epochs**:
   - High-order boundary advances (e.g. node reboots, policy updates, epoch rollovers) increment the `causal_epoch`.
   - Any transaction carrying an outdated epoch fails closed under `ERR_STALE_PRE_STATE`.

3. **Validity Intervals for Observations**:
   Every sensor observation carries an explicit validity interval $\Delta t_{\text{valid}}$:
   $$\text{Valid at evaluation time } t \iff t_{\text{received}} - t_{\text{observed}} \le T_{\text{max\_staleness}}$$
   If staleness exceeds threshold, observation is invalidated and cannot satisfy transition triggers.
