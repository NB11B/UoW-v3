# COBOL Fixed-Width Batch Card Mapping

This specification defines how 80-column and 1024-byte mainframe batch records map to the canonical `UoWEnvelope` and `UoWResult` JSON schemas.

## Inbound Request Card (Record Length: 1024 bytes)

| Columns | Field Name | Description | JSON Path |
|---|---|---|---|
| 0001 - 0008 | `UOW-PROTOCOL-VERSION` | Protocol version (`1.0.0   `) | `$.protocol_version` |
| 0009 - 0072 | `UOW-OPERATION-ID` | Canonical operation ID | `$.operation` |
| 0073 - 0080 | `UOW-OPERATION-VERSION` | Operation version (`1.0.0   `) | `$.operation_version` |
| 0081 - 0116 | `UOW-REQUEST-ID` | Unique request UUID | `$.request_id` |
| 0117 - 0152 | `UOW-CORRELATION-ID` | Causal flow UUID | `$.correlation_id` |
| 0153 - 0184 | `UOW-ACTOR-ID` | Mainframe operator / batch ID | `$.actor.id` |
| 0185 - 0200 | `UOW-ACTOR-ROLE` | Role (`BATCH_JOB       `) | `$.actor.role` |
| 0201 - 0220 | `UOW-ACTOR-CLAIM-TYPE` | Claim classification | `$.actor.claim_type` |
| 0221 - 0284 | `UOW-AUTH-TOKEN` | RACF / cryptographic ticket | `$.authority_context.tokens[0]` |
| 0285 - 0348 | `UOW-IDEMPOTENCY-KEY` | Batch transaction key | `$.constraints.idempotency_key` |
| 0349 - 0412 | `UOW-PARENT-EVID-HASH`| Previous ledger hash (chain) | `$.evidence_context.parent_evidence_hash` |
| 0413 - 0476 | `UOW-REPLY-TO` | Output queue / dataset name | `$.reply_to` |
| 0477 - 0480 | `UOW-PAYLOAD-LENGTH` | Big-endian length of data | Length of `$.payload` |
| 0481 - 0992 | `UOW-PAYLOAD-DATA` | Serialized JSON or EBCDIC | `$.payload` |
| 0993 - 1024 | `UOW-RESERVED` | Padding for record alignment | N/A |
