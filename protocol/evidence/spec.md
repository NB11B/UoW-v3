# Canonical Evidence Specification: Witness Obligations & Ledger Integrity

## 1. Evidence Record Invariant

Every committed Unit of Work produces an immutable witness obligation:

$$E = (\text{step}, H_{\text{pre}}, H_{\text{post}}, H_{\pi}, H_{\sigma}, H_{\text{prev}}, H_{\text{rec}})$$

Where:
* $\text{step}$: Non-decreasing monotonic sequence index in ledger.
* $H_{\text{pre}}$: 64-character hex SHA-256 fingerprint of `WorldState` before transition.
* $H_{\text{post}}$: 64-character hex SHA-256 fingerprint of `WorldState` after deterministic mutation.
* $H_{\pi}$: 64-character hex SHA-256 of candidate proposal $\pi$.
* $H_{\sigma}$: 64-character hex SHA-256 of certification record $\sigma$.
* $H_{\text{prev}}$: 64-character hex SHA-256 of immediately preceding evidence record ($0^{64}$ for genesis).
* $H_{\text{rec}}$: Canonical SHA-256 hash computed over $(H_{\text{pre}} \parallel H_{\text{post}} \parallel H_{\pi} \parallel H_{\sigma} \parallel H_{\text{prev}})$.

---

## 2. Cross-Language Conformance Rules

1. **Hash Chain Continuity**: An evidence ledger is valid if and only if for all $i > 0$, $E_i.H_{\text{prev}} == E_{i-1}.H_{\text{rec}}$.
2. **Deterministic Certification**: Given identical state and proposal, certifiers across all languages (Python, TypeScript, Rust, C) must compute identical $H_{\sigma}$ and identical pass/reject outcome.
3. **Fail-Closed Verification**: Any bit modification in $H_{\text{post}}$, route index, or mutation operand invalidates $H_{\text{rec}}$ and terminates execution under `ERR_ROUTE_DIVERGENCE`.
