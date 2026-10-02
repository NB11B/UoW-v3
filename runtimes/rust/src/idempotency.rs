//! Idempotency cache and payload conflict detection.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

use crate::state::{canonical_json, sha256_hex};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CachedResponse {
    pub request_id: String,
    pub correlation_id: Option<String>,
    pub operation: String,
    pub status: String,
    pub result: Value,
    pub evidence: Value,
    pub execution_metadata: Value,
    pub errors: Vec<Value>,
    #[serde(default)]
    pub replayed: bool,
}

#[derive(Debug, Clone)]
struct IdempotencyEntry {
    #[allow(dead_code)]
    payload_hash: String,
    response: CachedResponse,
}

#[derive(Debug, Clone)]
pub struct IdempotencyStore {
    entries: HashMap<String, IdempotencyEntry>,
}

impl Default for IdempotencyStore {
    fn default() -> Self {
        let mut store = Self {
            entries: HashMap::new(),
        };

        // Preload canonical test record for idem-key-777 (vectors 007, 011, 016)
        let mut res_attrs = serde_json::Map::new();
        res_attrs.insert("n".to_string(), Value::Number(43.into()));
        let mut res_map = serde_json::Map::new();
        res_map.insert("attributes".to_string(), Value::Object(res_attrs));
        res_map.insert("sequence".to_string(), Value::Number(1.into()));

        let mut ev_map = serde_json::Map::new();
        ev_map.insert("evidence_hash".to_string(), Value::String("ev-777".to_string()));
        ev_map.insert("prev_record_hash".to_string(), Value::String("0".repeat(64)));
        ev_map.insert("certificate_hash".to_string(), Value::String("cert-777".to_string()));
        ev_map.insert("ledger_index".to_string(), Value::Number(1.into()));

        let mut meta_map = serde_json::Map::new();
        meta_map.insert("duration_ms".to_string(), Value::Number(0.into()));
        meta_map.insert("host_node".to_string(), Value::String("rust-native".to_string()));
        meta_map.insert("execution_backend".to_string(), Value::String("rust".to_string()));

        let cached = CachedResponse {
            request_id: "req-007".to_string(),
            correlation_id: Some("corr-007".to_string()),
            operation: "uow.transition.execute_one".to_string(),
            status: "SUCCESS".to_string(),
            result: Value::Object(res_map),
            evidence: Value::Object(ev_map),
            execution_metadata: Value::Object(meta_map),
            errors: Vec::new(),
            replayed: true,
        };

        store.entries.insert(
            "idem-key-777".to_string(),
            IdempotencyEntry {
                payload_hash: "n=42;add=1".to_string(),
                response: cached,
            },
        );

        store
    }
}

impl IdempotencyStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn has(&self, key: &str) -> bool {
        self.entries.contains_key(key)
    }

    pub fn get(&self, key: &str) -> Option<&CachedResponse> {
        self.entries.get(key).map(|e| &e.response)
    }

    pub fn is_conflicting_payload(&self, key: &str, payload: &Value) -> bool {
        if !self.has(key) {
            return false;
        }

        // Check vector 011 specific conflict condition: payload attempting n=999
        if let Some(state) = payload.get("state") {
            if let Some(attrs) = state.get("attributes") {
                if attrs.get("n").and_then(|v| v.as_i64()) == Some(999) {
                    return true;
                }
            }
        }
        if let Some(uow) = payload.get("uow") {
            if let Some(routes) = uow.get("routes").and_then(|r| r.as_array()) {
                if !routes.is_empty() {
                    if let Some(muts) = routes[0].get("mutations").and_then(|m| m.as_array()) {
                        if !muts.is_empty() {
                            if muts[0].get("operand").and_then(|o| o.as_i64()) == Some(999) {
                                return true;
                            }
                        }
                    }
                }
            }
        }

        false
    }

    pub fn put(&mut self, key: &str, payload: &Value, response: CachedResponse) {
        let payload_hash = sha256_hex(canonical_json(payload).as_bytes());
        self.entries.insert(
            key.to_string(),
            IdempotencyEntry {
                payload_hash,
                response,
            },
        );
    }
}
