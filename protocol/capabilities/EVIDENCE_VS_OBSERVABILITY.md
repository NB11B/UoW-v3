# Substrate Specification: Evidence versus Observability

## 1. Executive Distinction

$$\boxed{\text{Evidence} \neq \text{Observability}}$$

Modern software architectures frequently collapse all telemetry, metrics, debug logs, and audit trails into a single logging pipeline. In high-assurance distributed systems, this conflation is a severe hazard:
* If debug logs are treated as proof, forged log lines can fabricate execution receipts.
* If every ephemeral trace span is added to the cryptographic hash chain, ledger throughput collapses under massive non-essential payload bloat.

UoW v2.0 strictly separates **Evidence** from **Observability**:

$$\begin{array}{|l|l|l|}
\hline
\textbf{Dimension} & \textbf{Evidence (Proof)} & \textbf{Observability (Diagnostics)} \\
\hline
\textbf{Purpose} & \text{Proves legally \& cryptographically what happened} & \text{Explains operationally what is happening} \\
\textbf{Immutability} & \textbf{Permanent, append-only, tamper-evident (WAL)} & \text{Ephemeral, TTL-bound, rolling retention} \\
\textbf{Integrity} & \text{Cryptographic signatures, SHA-256 hash chains} & \text{Best-effort, sampled, non-cryptographic} \\
\textbf{Consumer} & \text{Authority Kernel, External Auditors, Regulators} & \text{Human Operators, DevOps, Planning Heuristics} \\
\textbf{Failure Mode} & \text{Discontinuity halts execution (FAIL CLOSED)} & \text{Telemetry drop degrades monitoring, execution continues} \\
\textbf{Artifacts} & \text{Receipts, Certificates, Hashes, Attestations} & \text{Spans, Metrics, Histograms, Debug Logs} \\
\hline
\end{array}$$

---

## 2. Evidence Architecture

Evidence is recorded in the append-only `EvidenceLedger`. Every record $E_k$ satisfies:

$$E_k = \Big( \text{seq}_k, \; H_{\text{prev}}, \; H(S_k), \; \text{uow\_id}, \; \text{actor\_claim}, \; \sigma_{\text{cert}}, \; \text{timestamp} \Big)$$

Where:
$$H_{\text{prev}} = \text{SHA256}(E_{k-1})$$
Any tampering, missing record, or sequence alteration breaks the hash chain, causing immediate kernel panic and system halt under `ERR_EVIDENCE_DISCONTINUITY`.

---

## 3. Observability Architecture

Observability provides diagnostic telemetry for system health, latency monitoring, and agent planning heuristics:
1. **Traces**: OpenTelemetry-compatible span trees tracking end-to-end distributed execution.
2. **Metrics**: Real-time gauges and counters (QPS, memory residency, temperature, CPU saturation).
3. **Diagnostic Logs**: Unstructured or structured context messages explaining reasoning steps.

### Boundary Invariant:
An autonomous agent or heuristic scheduler may freely consume **observability metrics** to optimize proposal generation. However, the **Authority Kernel certifying a transition relies strictly on cryptographic evidence**.
