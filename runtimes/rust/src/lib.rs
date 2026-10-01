//! # Canonical Unit-of-Work (UoW) Core SDK (Rust)
//!
//! Provides native Rust models, canonical JSON serialization, deterministic validation,
//! and C-compatible ABI interfaces.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_int};

#[allow(non_camel_case_types)]
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ClaimType {
    UNVERIFIED_CLAIM,
    AUTHENTICATED,
    DELEGATED,
    QUORUM_CERTIFIED,
}

impl Default for ClaimType {
    fn default() -> Self {
        ClaimType::UNVERIFIED_CLAIM
    }
}

#[allow(non_camel_case_types)]
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum UoWStatus {
    SUCCESS,
    REJECTED,
    ERROR,
    PENDING,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Actor {
    pub id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
    #[serde(default)]
    pub claim_type: ClaimType,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub key_fingerprint: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct DelegationSpec {
    pub delegator: String,
    pub delegatee: String,
    pub scope: String,
    pub signature: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct AuthorityContext {
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tokens: Vec<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub delegations: Vec<DelegationSpec>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct Constraints {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeout_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub idempotency_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub causal_epoch: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deadline: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct EvidenceContext {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_evidence_hash: Option<String>,
    #[serde(default)]
    pub require_hash_chain: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UoWEnvelope<T = serde_json::Value> {
    pub protocol_version: String,
    pub operation: String,
    pub operation_version: String,
    pub request_id: String,
    pub correlation_id: String,
    pub actor: Actor,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub authority_context: Option<AuthorityContext>,
    pub payload: T,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub constraints: Option<Constraints>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub evidence_context: Option<EvidenceContext>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reply_to: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EvidenceRecord {
    pub evidence_hash: String,
    pub prev_record_hash: String,
    pub certificate_hash: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pre_state_hash: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub post_state_hash: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub proposal_hash: Option<String>,
    pub ledger_index: u64,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub signatures: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExecutionMetadata {
    pub duration_ms: f64,
    pub host_node: String,
    pub execution_backend: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timestamp: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct UoWError {
    pub code: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(default)]
    pub retryable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UoWResult<R = serde_json::Value> {
    pub request_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<String>,
    pub operation: String,
    pub status: UoWStatus,
    pub result: R,
    pub evidence: EvidenceRecord,
    pub execution_metadata: ExecutionMetadata,
    pub errors: Vec<UoWError>,
}

/// Compute SHA-256 hex digest
pub fn sha256_hex(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hex::encode(hasher.finalize())
}

// ---------------------------------------------------------------------------
// C ABI Export Layer
// ---------------------------------------------------------------------------

#[no_mangle]
pub unsafe extern "C" fn uow_free_string(ptr: *mut c_char) {
    if !ptr.is_null() {
        let _ = CString::from_raw(ptr);
    }
}

#[no_mangle]
pub unsafe extern "C" fn uow_validate_envelope(envelope_json: *const c_char) -> c_int {
    if envelope_json.is_null() {
        return -1;
    }
    let c_str = CStr::from_ptr(envelope_json);
    let slice = match c_str.to_str() {
        Ok(s) => s,
        Err(_) => return -2,
    };
    match serde_json::from_str::<UoWEnvelope>(slice) {
        Ok(_) => 0,
        Err(_) => 1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_envelope_serde_roundtrip() {
        let envelope = UoWEnvelope {
            protocol_version: "1.0.0".to_string(),
            operation: "uow.transition.execute_one".to_string(),
            operation_version: "1.0.0".to_string(),
            request_id: "req-rust-test".to_string(),
            correlation_id: "corr-rust-test".to_string(),
            actor: Actor {
                id: "rust-tester".to_string(),
                role: Some("test".to_string()),
                claim_type: ClaimType::AUTHENTICATED,
                key_fingerprint: None,
            },
            authority_context: None,
            payload: serde_json::json!({"counter": 42}),
            constraints: None,
            evidence_context: None,
            reply_to: None,
        };

        let json_str = serde_json::to_string(&envelope).expect("serialization failed");
        let deserialized: UoWEnvelope = serde_json::from_str(&json_str).expect("deserialization failed");
        assert_eq!(envelope, deserialized);
    }

    #[test]
    fn test_c_abi_validation() {
        let valid_json = r#"{"protocol_version":"1.0.0","operation":"inventory.reserve","operation_version":"1.0.0","request_id":"req-c","correlation_id":"corr-c","actor":{"id":"c-user"},"payload":{}}"#;
        let c_str = CString::new(valid_json).unwrap();
        let res = unsafe { uow_validate_envelope(c_str.as_ptr()) };
        assert_eq!(res, 0);

        let invalid_json = r#"{"invalid":"envelope"}"#;
        let c_str_invalid = CString::new(invalid_json).unwrap();
        let res_invalid = unsafe { uow_validate_envelope(c_str_invalid.as_ptr()) };
        assert_eq!(res_invalid, 1);
    }
}
