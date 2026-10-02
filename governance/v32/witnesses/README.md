# UoW v3.2 Witness Registry

This directory contains the immutable deficit witness records for the **v3.2** lifecycle.

---

## Registry Rules

1. **No Speculative Entries**:
   Do not pre-populate or create placeholder witness files (e.g. `V32-W0001`) in advance of an observed, reproducible deficit.
   \[
   \boxed{
   \text{No Witness}
   \implies
   \text{No Campaign}
   \implies
   \text{No New Architecture}
   }
   \]

2. **File Naming Convention**:
   Each witness record must be named:
   ```text
   V32-W<XXXX>_<short_slug>.yaml
   ```
   Example: `V32-W0001_pci_hsm_attestation_failure.yaml`.

3. **Intake Requirement**:
   Witnesses are created by copying [`../WITNESS_TEMPLATE.yaml`](../WITNESS_TEMPLATE.yaml) and populating all required fields.

4. **Validation**:
   All files in this directory are validated in CI and locally via:
   ```powershell
   python -m qualification.v32_intake --validate-all
   ```
