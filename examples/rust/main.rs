//! UoW Polyglot Architecture - Rust Example
//!
//! Demonstrates constructing and serializing a canonical UoWEnvelope in Rust.

use uow_core::{Actor, ClaimType, Constraints, UoWEnvelope};

fn main() {
    println!("=== UoW Polyglot Interoperability Demo (Rust) ===");

    let envelope = UoWEnvelope {
        protocol_version: "1.0.0".to_string(),
        operation: "inventory.reserve".to_string(),
        operation_version: "1.0.0".to_string(),
        request_id: "req-rust-001".to_string(),
        correlation_id: "corr-rust-001".to_string(),
        actor: Actor {
            id: "rust-worker-01".to_string(),
            role: Some("embedded-device".to_string()),
            claim_type: ClaimType::AUTHENTICATED,
            key_fingerprint: None,
        },
        authority_context: None,
        payload: serde_json::json!({
            "sku": "WIDGET-99",
            "quantity": 2,
            "order_id": "ORD-RUST-002"
        }),
        constraints: Some(Constraints {
            idempotency_key: Some("idem-rust-002".to_string()),
            timeout_ms: Some(1000),
            causal_epoch: None,
            deadline: None,
        }),
        evidence_context: None,
        reply_to: None,
    };

    let serialized = serde_json::to_string_pretty(&envelope).unwrap();
    println!("Serialized Rust Envelope:\n{}", serialized);
}
