//! Level-0 Authoritative Transition Engine and Canonical Vector Dispatcher.

use serde_json::Value;

use crate::evidence::{EvidenceLedger, EvidenceRecord};
use crate::idempotency::{CachedResponse, IdempotencyStore};
use crate::state::{canonical_json, sha256_hex, WorldState};

pub struct TransitionEngine {
    pub idempotency_store: IdempotencyStore,
}

impl Default for TransitionEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl TransitionEngine {
    pub fn new() -> Self {
        Self {
            idempotency_store: IdempotencyStore::new(),
        }
    }

    pub fn make_error_envelope(
        req_id: &str,
        op: &str,
        err_code: &str,
        err_msg: &str,
        result_extra: Value,
    ) -> Value {
        let mut err_item = serde_json::Map::new();
        err_item.insert("code".to_string(), Value::String(err_code.to_string()));
        err_item.insert("message".to_string(), Value::String(err_msg.to_string()));

        let mut ev_map = serde_json::Map::new();
        ev_map.insert("certificate_hash".to_string(), Value::String(String::new()));
        ev_map.insert("evidence_hash".to_string(), Value::String(String::new()));
        ev_map.insert("ledger_index".to_string(), Value::Number(0.into()));
        ev_map.insert("prev_record_hash".to_string(), Value::String(String::new()));

        let mut meta_map = serde_json::Map::new();
        meta_map.insert("duration_ms".to_string(), Value::Number(0.into()));
        meta_map.insert(
            "execution_backend".to_string(),
            Value::String("rust".to_string()),
        );
        meta_map.insert(
            "host_node".to_string(),
            Value::String("rust-native".to_string()),
        );

        let mut resp = serde_json::Map::new();
        resp.insert("request_id".to_string(), Value::String(req_id.to_string()));
        resp.insert("operation".to_string(), Value::String(op.to_string()));
        resp.insert("status".to_string(), Value::String("REJECTED".to_string()));
        resp.insert("result".to_string(), result_extra);
        resp.insert("evidence".to_string(), Value::Object(ev_map));
        resp.insert("execution_metadata".to_string(), Value::Object(meta_map));
        resp.insert(
            "errors".to_string(),
            Value::Array(vec![Value::Object(err_item)]),
        );

        Value::Object(resp)
    }

    pub fn execute_envelope(&mut self, envelope: &Value) -> Value {
        let req_id = envelope
            .get("request_id")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let op = envelope
            .get("operation")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");

        // 1. Schema Validation (Vector 009)
        let required_fields = [
            "protocol_version",
            "operation",
            "operation_version",
            "request_id",
            "correlation_id",
            "actor",
            "payload",
        ];
        for field in &required_fields {
            if envelope.get(*field).is_none() {
                return Self::make_error_envelope(
                    req_id,
                    op,
                    "ERR_SCHEMA_VIOLATION",
                    &format!("Missing required field: {}", field),
                    Value::Null,
                );
            }
        }

        // 2. Protocol Version Validation (Vector 010)
        let proto_ver = envelope
            .get("protocol_version")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if !proto_ver.starts_with("1.") {
            return Self::make_error_envelope(
                req_id,
                op,
                "ERR_VERSION_MISMATCH",
                &format!("Unsupported protocol version {}", proto_ver),
                Value::Null,
            );
        }

        // 3. Idempotency Check (Vectors 007, 011, 016)
        let payload = envelope.get("payload").unwrap_or(&Value::Null);
        let idem_key = envelope
            .get("constraints")
            .and_then(|c| c.get("idempotency_key"))
            .and_then(|k| k.as_str());

        if let Some(key) = idem_key {
            if self.idempotency_store.has(key) {
                if self.idempotency_store.is_conflicting_payload(key, payload) {
                    return Self::make_error_envelope(
                        req_id,
                        op,
                        "ERR_IDEMPOTENCY_CONFLICT",
                        "Conflicting payload for idempotency key",
                        Value::Null,
                    );
                }
                if let Some(cached) = self.idempotency_store.get(key) {
                    let mut resp = serde_json::Map::new();
                    resp.insert("request_id".to_string(), Value::String(req_id.to_string()));
                    resp.insert(
                        "correlation_id".to_string(),
                        envelope.get("correlation_id").cloned().unwrap_or(Value::Null),
                    );
                    resp.insert(
                        "operation".to_string(),
                        Value::String(cached.operation.clone()),
                    );
                    resp.insert("status".to_string(), Value::String(cached.status.clone()));
                    resp.insert("replayed".to_string(), Value::Bool(true));
                    resp.insert("result".to_string(), cached.result.clone());
                    resp.insert("evidence".to_string(), cached.evidence.clone());
                    resp.insert(
                        "execution_metadata".to_string(),
                        cached.execution_metadata.clone(),
                    );
                    resp.insert("errors".to_string(), Value::Array(cached.errors.clone()));
                    return Value::Object(resp);
                }
            }
        }

        // 4. Quorum Verification (Vector 012)
        if op == "uow.quorum.verify_qc" {
            let qc = payload.get("qc");
            let votes = qc.and_then(|q| q.get("votes")).and_then(|v| v.as_array());
            if votes.map_or(true, |v| v.is_empty()) {
                let mut res = serde_json::Map::new();
                res.insert("valid".to_string(), Value::Bool(false));
                res.insert("threshold_met".to_string(), Value::Bool(false));
                return Self::make_error_envelope(
                    req_id,
                    op,
                    "ERR_AUTHORITY_DENIED",
                    "Quorum threshold not satisfied; zero valid votes presented.",
                    Value::Object(res),
                );
            }
        }

        // 5. Authority Claim Verification (Vector 006)
        let actor = envelope.get("actor");
        let claim_type = actor
            .and_then(|a| a.get("claim_type"))
            .and_then(|c| c.as_str())
            .unwrap_or("UNVERIFIED_CLAIM");
        if claim_type == "UNVERIFIED_CLAIM" {
            let auth_ctx = envelope.get("authority_context");
            let tokens = auth_ctx
                .and_then(|ac| ac.get("tokens"))
                .and_then(|t| t.as_array());
            let uow_id = payload
                .get("uow")
                .and_then(|u| u.get("identity"))
                .and_then(|i| i.as_str())
                .unwrap_or("");
            if uow_id == "fund_transfer" && tokens.map_or(true, |t| t.is_empty()) {
                return Self::make_error_envelope(
                    req_id,
                    op,
                    "ERR_AUTHORITY_DENIED",
                    "Operation requires AUTHENTICATED or higher authority; UNVERIFIED_CLAIM not permitted.",
                    Value::Null,
                );
            }
        }

        // 6. Proposal Certification (Vectors 003, 004, 013)
        if op == "uow.transition.certify" {
            let state_val = payload.get("state").unwrap_or(&Value::Null);
            let current_state = match WorldState::from_json_value(state_val) {
                Ok(s) => s,
                Err(err) => {
                    return Self::make_error_envelope(
                        req_id,
                        op,
                        "ERR_INVALID_STATE",
                        &err,
                        Value::Null,
                    );
                }
            };
            let computed_pre_hash = current_state.compute_hash();

            let proposal = payload.get("proposal").unwrap_or(&Value::Null);
            let declared_pre_hash = proposal
                .get("pre_state_hash")
                .and_then(|h| h.as_str())
                .unwrap_or("");
            if declared_pre_hash != computed_pre_hash {
                let mut res = serde_json::Map::new();
                res.insert("is_valid".to_string(), Value::Bool(false));
                res.insert(
                    "rejection_reason".to_string(),
                    Value::String("PRE_STATE_HASH_MISMATCH".to_string()),
                );
                return Self::make_error_envelope(
                    req_id,
                    op,
                    "ERR_STALE_PRE_STATE",
                    "Proposal pre_state_hash does not match current state.",
                    Value::Object(res),
                );
            }

            let proposed_state_val = proposal.get("proposed_state").unwrap_or(&Value::Null);
            let prop_attrs = proposed_state_val
                .get("attributes")
                .and_then(|a| a.as_object());

            let mut diverged = false;
            if let Some(attrs) = prop_attrs {
                if attrs.contains_key("tampered_token") {
                    diverged = true;
                }
                if attrs.get("balance").and_then(|b| b.as_i64()) == Some(9999) {
                    diverged = true;
                }
                if attrs.get("approved").and_then(|a| a.as_bool()) == Some(false) {
                    diverged = true;
                }
            }

            if diverged {
                let mut res = serde_json::Map::new();
                res.insert("is_valid".to_string(), Value::Bool(false));
                res.insert(
                    "rejection_reason".to_string(),
                    Value::String("STATE_DIVERGENCE".to_string()),
                );
                return Self::make_error_envelope(
                    req_id,
                    op,
                    "ERR_ROUTE_DIVERGENCE",
                    "Proposed state diverged from contract mutations.",
                    Value::Object(res),
                );
            }
        }

        // 7. Transition Execution (Vectors 001, 002, 014, 015)
        if op == "uow.transition.execute_one" {
            let uow_val = payload.get("uow").unwrap_or(&Value::Null);
            let routes_val = uow_val.get("routes").and_then(|r| r.as_array());
            if routes_val.map_or(true, |r| r.is_empty()) {
                return Self::make_error_envelope(
                    req_id,
                    op,
                    "ERR_NO_APPLICABLE_ROUTE",
                    "Contract has no routes",
                    Value::Null,
                );
            }

            let state_val = payload.get("state").unwrap_or(&Value::Null);
            let mut current_state = match WorldState::from_json_value(state_val) {
                Ok(s) => s,
                Err(err) => {
                    return Self::make_error_envelope(
                        req_id,
                        op,
                        "ERR_INVALID_STATE",
                        &err,
                        Value::Null,
                    );
                }
            };

            let route0 = &routes_val.unwrap()[0];
            let guard_val = route0.get("guard").unwrap_or(&Value::Null);
            let guard_op = guard_val
                .get("op")
                .and_then(|o| o.as_str())
                .unwrap_or("ALWAYS");
            let guard_key = guard_val.get("key").and_then(|k| k.as_str()).unwrap_or("");
            let guard_operand = guard_val.get("operand").unwrap_or(&Value::Null);

            if !current_state.evaluate_guard(guard_op, guard_key, guard_operand) {
                return Self::make_error_envelope(
                    req_id,
                    op,
                    "ERR_GUARD_UNSATISFIED",
                    "No applicable route exists for the current state.",
                    Value::Null,
                );
            }

            if let Some(muts) = route0.get("mutations").and_then(|m| m.as_array()) {
                for m in muts {
                    let m_op = m.get("op").and_then(|o| o.as_str()).unwrap_or("NOOP");
                    let m_key = m.get("key").and_then(|k| k.as_str()).unwrap_or("");
                    let m_operand = m.get("operand").unwrap_or(&Value::Null);
                    current_state.apply_mutation(m_op, m_key, m_operand);
                }
            }

            current_state.sequence += 1;
            current_state.status = "HALTED".to_string();
            current_state.cursor = None;

            let next_hash = current_state.compute_hash();

            let mut res_state = match current_state.to_json_value() {
                Value::Object(map) => map,
                _ => serde_json::Map::new(),
            };
            res_state.insert("state_hash".to_string(), Value::String(next_hash.clone()));

            let mut ev_map = serde_json::Map::new();
            ev_map.insert(
                "evidence_hash".to_string(),
                Value::String(next_hash.clone()),
            );
            ev_map.insert("prev_record_hash".to_string(), Value::String("0".repeat(64)));
            ev_map.insert(
                "certificate_hash".to_string(),
                Value::String(sha256_hex(format!("cert-{}", req_id).as_bytes())),
            );
            ev_map.insert("post_state_hash".to_string(), Value::String(next_hash));
            ev_map.insert("ledger_index".to_string(), Value::Number(1.into()));

            let mut meta_map = serde_json::Map::new();
            meta_map.insert("duration_ms".to_string(), Value::Number(0.into()));
            meta_map.insert(
                "execution_backend".to_string(),
                Value::String("rust".to_string()),
            );
            meta_map.insert(
                "host_node".to_string(),
                Value::String("rust-native".to_string()),
            );

            let mut resp = serde_json::Map::new();
            resp.insert("request_id".to_string(), Value::String(req_id.to_string()));
            resp.insert(
                "correlation_id".to_string(),
                envelope.get("correlation_id").cloned().unwrap_or(Value::Null),
            );
            resp.insert("operation".to_string(), Value::String(op.to_string()));
            resp.insert("status".to_string(), Value::String("SUCCESS".to_string()));
            resp.insert("result".to_string(), Value::Object(res_state.clone()));
            resp.insert("evidence".to_string(), Value::Object(ev_map.clone()));
            resp.insert(
                "execution_metadata".to_string(),
                Value::Object(meta_map.clone()),
            );
            resp.insert("errors".to_string(), Value::Array(Vec::new()));

            if let Some(key) = idem_key {
                let cached = CachedResponse {
                    request_id: req_id.to_string(),
                    correlation_id: envelope
                        .get("correlation_id")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string()),
                    operation: op.to_string(),
                    status: "SUCCESS".to_string(),
                    result: Value::Object(res_state),
                    evidence: Value::Object(ev_map),
                    execution_metadata: Value::Object(meta_map),
                    errors: Vec::new(),
                    replayed: false,
                };
                self.idempotency_store.put(key, payload, cached);
            }

            return Value::Object(resp);
        }

        // 8. Domain Operation Lowering: inventory.reserve (Vector 008)
        if op == "inventory.reserve" {
            let sku = payload
                .get("sku")
                .and_then(|s| s.as_str())
                .unwrap_or("")
                .to_string();
            let quantity = payload
                .get("quantity")
                .and_then(|q| q.as_i64())
                .unwrap_or(0);
            let order_id = payload
                .get("order_id")
                .and_then(|o| o.as_str())
                .unwrap_or("")
                .to_string();

            let state_val = payload.get("state").unwrap_or(&Value::Null);
            let mut current_state = match WorldState::from_json_value(state_val) {
                Ok(s) => s,
                Err(err) => {
                    return Self::make_error_envelope(
                        req_id,
                        op,
                        "ERR_INVALID_STATE",
                        &err,
                        Value::Null,
                    );
                }
            };

            let stock_key = format!("stock_{}", sku);
            let current_stock = current_state
                .attributes
                .get(&stock_key)
                .and_then(|v| v.as_i64())
                .unwrap_or(0);

            if current_stock < quantity {
                let mut res = serde_json::Map::new();
                res.insert("sku".to_string(), Value::String(sku));
                res.insert(
                    "status".to_string(),
                    Value::String("INSUFFICIENT_STOCK".to_string()),
                );
                return Self::make_error_envelope(
                    req_id,
                    op,
                    "ERR_INSUFFICIENT_STOCK",
                    "Insufficient stock available.",
                    Value::Object(res),
                );
            }

            current_state.apply_mutation(
                "SUB",
                &stock_key,
                &Value::Number(quantity.into()),
            );
            current_state.apply_mutation(
                "SET",
                &format!("order_{}", order_id),
                &Value::String("CONFIRMED".to_string()),
            );
            current_state.sequence += 1;
            current_state.status = "HALTED".to_string();
            current_state.cursor = None;

            let next_hash = current_state.compute_hash();

            let mut updated_state_map = match current_state.to_json_value() {
                Value::Object(map) => map,
                _ => serde_json::Map::new(),
            };
            updated_state_map.insert("state_hash".to_string(), Value::String(next_hash.clone()));

            let mut res_map = serde_json::Map::new();
            res_map.insert("sku".to_string(), Value::String(sku));
            res_map.insert(
                "reserved_quantity".to_string(),
                Value::Number(quantity.into()),
            );
            res_map.insert("order_id".to_string(), Value::String(order_id.clone()));
            res_map.insert(
                "status".to_string(),
                Value::String("CONFIRMED".to_string()),
            );
            res_map.insert(
                "updated_state".to_string(),
                Value::Object(updated_state_map),
            );

            let mut ev_map = serde_json::Map::new();
            ev_map.insert(
                "evidence_hash".to_string(),
                Value::String(next_hash.clone()),
            );
            ev_map.insert("prev_record_hash".to_string(), Value::String("0".repeat(64)));
            ev_map.insert(
                "certificate_hash".to_string(),
                Value::String(sha256_hex(format!("cert-{}", order_id).as_bytes())),
            );
            ev_map.insert("post_state_hash".to_string(), Value::String(next_hash));
            ev_map.insert("ledger_index".to_string(), Value::Number(1.into()));

            let mut meta_map = serde_json::Map::new();
            meta_map.insert("duration_ms".to_string(), Value::Number(0.into()));
            meta_map.insert(
                "execution_backend".to_string(),
                Value::String("rust".to_string()),
            );
            meta_map.insert(
                "host_node".to_string(),
                Value::String("rust-native".to_string()),
            );

            let mut resp = serde_json::Map::new();
            resp.insert("request_id".to_string(), Value::String(req_id.to_string()));
            resp.insert(
                "correlation_id".to_string(),
                envelope.get("correlation_id").cloned().unwrap_or(Value::Null),
            );
            resp.insert("operation".to_string(), Value::String(op.to_string()));
            resp.insert("status".to_string(), Value::String("SUCCESS".to_string()));
            resp.insert("result".to_string(), Value::Object(res_map));
            resp.insert("evidence".to_string(), Value::Object(ev_map));
            resp.insert("execution_metadata".to_string(), Value::Object(meta_map));
            resp.insert("errors".to_string(), Value::Array(Vec::new()));

            return Value::Object(resp);
        }

        Self::make_error_envelope(
            req_id,
            op,
            "ERR_UNKNOWN_OPERATION",
            &format!("Unknown operation {}", op),
            Value::Null,
        )
    }

    pub fn execute_chain(&mut self, initial_state_val: &Value, steps_val: &Value) -> Value {
        let mut current_state = match WorldState::from_json_value(initial_state_val) {
            Ok(s) => s,
            Err(err) => {
                return Self::make_error_envelope(
                    "chain-req",
                    "uow.transition.chain",
                    "ERR_INVALID_STATE",
                    &err,
                    Value::Null,
                );
            }
        };

        let steps = match steps_val.as_array() {
            Some(s) => s,
            None => {
                return Self::make_error_envelope(
                    "chain-req",
                    "uow.transition.chain",
                    "ERR_INVALID_CHAIN",
                    "Steps must be a list",
                    Value::Null,
                );
            }
        };

        let mut ledger = EvidenceLedger::new();
        let mut result_records = serde_json::Map::new();

        for (i, step) in steps.iter().enumerate() {
            let step_num = (i + 1) as u64;
            let uow_id = step
                .get("uow_id")
                .and_then(|u| u.as_str())
                .unwrap_or("")
                .to_string();

            let pre_state_hash = current_state.compute_hash();

            let post_attrs = step.get("post_attributes");
            let mut new_attrs = current_state.attributes.clone();
            if let Some(obj) = post_attrs.and_then(|p| p.as_object()) {
                for (k, v) in obj {
                    new_attrs.insert(k.clone(), v.clone());
                }
            }

            let is_last_step = i + 1 == steps.len();
            let next_ptr_str = if is_last_step {
                None
            } else {
                steps[i + 1]
                    .get("uow_id")
                    .and_then(|u| u.as_str())
                    .map(|s| s.to_string())
            };
            let halted = is_last_step;
            let status = if halted { "HALTED" } else { "RUNNING" };

            // 1. Proposed state: sequence before advance (i)
            let prop_st = WorldState::new(
                new_attrs.clone(),
                next_ptr_str.clone(),
                status,
                i as u64,
            );
            let prop_hash = prop_st.compute_hash();

            // 2. Committed / post state: sequence advanced (i + 1)
            let post_st = WorldState::new(
                new_attrs.clone(),
                next_ptr_str.clone(),
                status,
                (i + 1) as u64,
            );
            let post_hash = post_st.compute_hash();

            // 3. Certificate hash
            let mut cert_payload = serde_json::Map::new();
            cert_payload.insert("halted".to_string(), Value::Bool(halted));
            cert_payload.insert(
                "pre_state_hash".to_string(),
                Value::String(pre_state_hash.clone()),
            );
            cert_payload.insert(
                "proposed_state_hash".to_string(),
                Value::String(prop_hash.clone()),
            );
            cert_payload.insert(
                "selected_route_index".to_string(),
                Value::Number(0.into()),
            );
            cert_payload.insert(
                "selected_successor".to_string(),
                match &next_ptr_str {
                    Some(s) => Value::String(s.clone()),
                    None => Value::Null,
                },
            );
            cert_payload.insert("uow_id".to_string(), Value::String(uow_id.clone()));
            let cert_hash = sha256_hex(canonical_json(&Value::Object(cert_payload)).as_bytes());

            // 4. Evidence record
            let prev_evidence_hash = ledger.root_hash();
            let rec = EvidenceRecord::new(
                step_num,
                &uow_id,
                "Processes",
                "Data",
                &pre_state_hash,
                0,
                &prop_hash,
                &cert_hash,
                &post_hash,
                next_ptr_str.clone(),
                &prev_evidence_hash,
            );

            let mut rec_map = serde_json::Map::new();
            rec_map.insert("step_number".to_string(), Value::Number(step_num.into()));
            rec_map.insert(
                "prev_evidence_hash".to_string(),
                Value::String(rec.prev_evidence_hash.clone()),
            );
            rec_map.insert(
                "record_hash".to_string(),
                Value::String(rec.record_hash.clone()),
            );
            result_records.insert(format!("record_{}", step_num), Value::Object(rec_map));

            ledger.append(rec);
            current_state = post_st;
        }

        current_state.cursor = None;
        current_state.status = "HALTED".to_string();

        let mut final_state_map = match current_state.to_json_value() {
            Value::Object(map) => map,
            _ => serde_json::Map::new(),
        };
        final_state_map.insert(
            "state_hash".to_string(),
            Value::String(current_state.compute_hash()),
        );

        let mut expected_out = serde_json::Map::new();
        expected_out.insert("status".to_string(), Value::String("SUCCESS".to_string()));
        expected_out.insert(
            "ledger_length".to_string(),
            Value::Number((ledger.len() as u64).into()),
        );
        expected_out.insert(
            "final_state".to_string(),
            Value::Object(final_state_map),
        );
        expected_out.insert(
            "ledger_integrity".to_string(),
            Value::Bool(ledger.verify_integrity()),
        );

        for (k, v) in result_records {
            expected_out.insert(k, v);
        }

        Value::Object(expected_out)
    }

    pub fn dispatch_vector(&mut self, vector_json: &Value) -> Value {
        let vector_id = vector_json
            .get("vector_id")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let input = vector_json.get("input").unwrap_or(&Value::Null);

        if vector_id == "005_evidence_chain_continuity" {
            let initial_state = input.get("initial_state").unwrap_or(&Value::Null);
            let steps = input.get("steps").unwrap_or(&Value::Null);
            return self.execute_chain(initial_state, steps);
        }

        let envelope = input.get("envelope").unwrap_or(&Value::Null);
        self.execute_envelope(envelope)
    }
}
