//! Cryptographic evidence records, hash chaining, and ledger integrity.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::state::{canonical_json, sha256_hex};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EvidenceRecord {
    pub step_number: u64,
    pub uow_id: String,
    pub source_category: String,
    pub target_category: String,
    pub pre_state_hash: String,
    pub selected_route_index: usize,
    pub proposed_state_hash: String,
    pub certificate_hash: String,
    pub post_state_hash: String,
    pub next_uow_pointer: Option<String>,
    pub prev_evidence_hash: String,
    pub record_hash: String,
}

impl EvidenceRecord {
    pub fn new(
        step_number: u64,
        uow_id: &str,
        source_category: &str,
        target_category: &str,
        pre_state_hash: &str,
        selected_route_index: usize,
        proposed_state_hash: &str,
        certificate_hash: &str,
        post_state_hash: &str,
        next_uow_pointer: Option<String>,
        prev_evidence_hash: &str,
    ) -> Self {
        let mut rec = Self {
            step_number,
            uow_id: uow_id.to_string(),
            source_category: source_category.to_string(),
            target_category: target_category.to_string(),
            pre_state_hash: pre_state_hash.to_string(),
            selected_route_index,
            proposed_state_hash: proposed_state_hash.to_string(),
            certificate_hash: certificate_hash.to_string(),
            post_state_hash: post_state_hash.to_string(),
            next_uow_pointer,
            prev_evidence_hash: prev_evidence_hash.to_string(),
            record_hash: String::new(),
        };
        rec.record_hash = rec.calculate_hash();
        rec
    }

    pub fn calculate_hash(&self) -> String {
        let mut map = serde_json::Map::new();
        map.insert(
            "certificate_hash".to_string(),
            Value::String(self.certificate_hash.clone()),
        );
        map.insert(
            "next_uow_pointer".to_string(),
            match &self.next_uow_pointer {
                Some(p) => Value::String(p.clone()),
                None => Value::Null,
            },
        );
        map.insert(
            "post_state_hash".to_string(),
            Value::String(self.post_state_hash.clone()),
        );
        map.insert(
            "pre_state_hash".to_string(),
            Value::String(self.pre_state_hash.clone()),
        );
        map.insert(
            "prev_evidence_hash".to_string(),
            Value::String(self.prev_evidence_hash.clone()),
        );
        map.insert(
            "proposed_state_hash".to_string(),
            Value::String(self.proposed_state_hash.clone()),
        );
        map.insert(
            "selected_route_index".to_string(),
            Value::Number(self.selected_route_index.into()),
        );
        map.insert(
            "source_category".to_string(),
            Value::String(self.source_category.clone()),
        );
        map.insert(
            "step_number".to_string(),
            Value::Number(self.step_number.into()),
        );
        map.insert(
            "target_category".to_string(),
            Value::String(self.target_category.clone()),
        );
        map.insert("uow_id".to_string(), Value::String(self.uow_id.clone()));

        let canonical_str = canonical_json(&Value::Object(map));
        sha256_hex(canonical_str.as_bytes())
    }

    pub fn to_json_value(&self) -> Value {
        serde_json::to_value(self).unwrap_or(Value::Null)
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct EvidenceLedger {
    pub records: Vec<EvidenceRecord>,
}

impl EvidenceLedger {
    pub fn new() -> Self {
        Self {
            records: Vec::new(),
        }
    }

    pub fn root_hash(&self) -> String {
        self.records
            .last()
            .map(|r| r.record_hash.clone())
            .unwrap_or_else(|| "0".repeat(64))
    }

    pub fn len(&self) -> usize {
        self.records.len()
    }

    pub fn is_empty(&self) -> bool {
        self.records.is_empty()
    }

    pub fn append(&mut self, record: EvidenceRecord) {
        self.records.push(record);
    }

    pub fn verify_integrity(&self) -> bool {
        let mut expected_prev = "0".repeat(64);
        for record in &self.records {
            if record.prev_evidence_hash != expected_prev {
                return false;
            }
            if record.record_hash != record.calculate_hash() {
                return false;
            }
            expected_prev = record.record_hash.clone();
        }
        true
    }
}
