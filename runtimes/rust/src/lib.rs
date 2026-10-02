//! # Canonical Unit-of-Work (UoW) Native Rust Runtime (v3.1)
//!
//! Provides independent execution authority for:
//! - Level 0: Authoritative Transitions (PROPOSE -> CERTIFY -> COMMIT), canonical JSON, hashing, guards, mutations, evidence chaining, and idempotency.
//! - Level 1: OCC transaction footprint checking, collision detection, deterministic sequencing, Write-Ahead Logging (WAL), and crash replay.
//! - Level 2: Deterministic DAG orchestration, task dependency frontier resolution, cycle defense, and halt detection.

pub mod engine;
pub mod evidence;
pub mod idempotency;
pub mod orchestration;
pub mod state;
pub mod transactions;
pub mod wal;

// Re-export core types
pub use engine::TransitionEngine;
pub use evidence::{EvidenceLedger, EvidenceRecord};
pub use idempotency::{CachedResponse, IdempotencyStore};
pub use orchestration::{DagError, OrchestrationDAG};
pub use state::{canonical_json, sha256_hex, WorldState};
pub use transactions::{
    CommittedTxRecord, DeterministicSequencer, OccDisposition, OccHazard, OccTracker,
    TransactionDescriptor,
};
pub use wal::{WalRecord, WALSequencer};
