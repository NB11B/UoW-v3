//! Authoritative, cryptographic WorldState and RFC-8785 canonical serialization.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt::Write as FmtWrite;

/// Compute SHA-256 hex digest
pub fn sha256_hex(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hex::encode(hasher.finalize())
}

/// RFC-8785 canonical JSON serializer matching Python reference:
/// `json.dumps(val, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`
pub fn canonical_json(val: &Value) -> String {
    match val {
        Value::Null => "null".to_string(),
        Value::Bool(b) => {
            if *b {
                "true".to_string()
            } else {
                "false".to_string()
            }
        }
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.to_string()
            } else if let Some(u) = n.as_u64() {
                u.to_string()
            } else if let Some(f) = n.as_f64() {
                if f.fract() == 0.0 && f.abs() < 1e16 {
                    format!("{:.1}", f)
                } else {
                    f.to_string()
                }
            } else {
                n.to_string()
            }
        }
        Value::String(s) => {
            let mut out = String::with_capacity(s.len() + 2);
            out.push('"');
            for c in s.chars() {
                match c {
                    '"' => out.push_str("\\\""),
                    '\\' => out.push_str("\\\\"),
                    '\x08' => out.push_str("\\b"),
                    '\x0C' => out.push_str("\\f"),
                    '\n' => out.push_str("\\n"),
                    '\r' => out.push_str("\\r"),
                    '\t' => out.push_str("\\t"),
                    c if (c as u32) < 0x20 => {
                        let _ = write!(out, "\\u{:04x}", c as u32);
                    }
                    c => out.push(c),
                }
            }
            out.push('"');
            out
        }
        Value::Array(arr) => {
            let items: Vec<String> = arr.iter().map(canonical_json).collect();
            format!("[{}]", items.join(","))
        }
        Value::Object(obj) => {
            let mut sorted_keys: Vec<&String> = obj.keys().collect();
            sorted_keys.sort();
            let mut entries = Vec::with_capacity(sorted_keys.len());
            for k in sorted_keys {
                let v = &obj[k];
                let escaped_key = canonical_json(&Value::String(k.clone()));
                entries.push(format!("{}:{}", escaped_key, canonical_json(v)));
            }
            format!("{{{}}}", entries.join(","))
        }
    }
}

/// Authoritative immutable WorldState
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WorldState {
    pub attributes: BTreeMap<String, Value>,
    pub cursor: Option<String>,
    pub status: String,
    pub sequence: u64,
    pub state_hash: String,
}

impl Default for WorldState {
    fn default() -> Self {
        Self::new(BTreeMap::new(), None, "RUNNING", 0)
    }
}

impl WorldState {
    pub fn new(
        attributes: BTreeMap<String, Value>,
        cursor: Option<String>,
        status: &str,
        sequence: u64,
    ) -> Self {
        let mut s = Self {
            attributes,
            cursor,
            status: status.to_string(),
            sequence,
            state_hash: String::new(),
        };
        s.state_hash = s.compute_hash();
        s
    }

    pub fn from_json_value(val: &Value) -> Result<Self, String> {
        let attrs_val = val.get("attributes").unwrap_or(val);
        let mut attributes = BTreeMap::new();
        if let Some(obj) = attrs_val.as_object() {
            for (k, v) in obj {
                if k != "cursor" && k != "status" && k != "sequence" && k != "state_hash" {
                    attributes.insert(k.clone(), v.clone());
                }
            }
        }

        let cursor = val
            .get("cursor")
            .and_then(|c| c.as_str())
            .map(|s| s.to_string());
        let status = val
            .get("status")
            .and_then(|s| s.as_str())
            .unwrap_or("RUNNING");
        let sequence = val
            .get("sequence")
            .and_then(|s| s.as_u64())
            .unwrap_or(0);

        Ok(Self::new(attributes, cursor, status, sequence))
    }

    pub fn compute_hash(&self) -> String {
        let mut map = serde_json::Map::new();
        let mut attrs_obj = serde_json::Map::new();
        for (k, v) in &self.attributes {
            attrs_obj.insert(k.clone(), v.clone());
        }
        map.insert("attributes".to_string(), Value::Object(attrs_obj));
        map.insert(
            "cursor".to_string(),
            match &self.cursor {
                Some(c) => Value::String(c.clone()),
                None => Value::Null,
            },
        );
        map.insert("sequence".to_string(), Value::Number(self.sequence.into()));
        map.insert("status".to_string(), Value::String(self.status.clone()));

        let canonical_str = canonical_json(&Value::Object(map));
        sha256_hex(canonical_str.as_bytes())
    }

    pub fn get(&self, key: &str) -> Option<&Value> {
        self.attributes.get(key)
    }

    pub fn with_attribute(&self, key: &str, val: Value) -> Self {
        let mut attrs = self.attributes.clone();
        attrs.insert(key.to_string(), val);
        Self::new(attrs, self.cursor.clone(), &self.status, self.sequence)
    }

    pub fn without_attribute(&self, key: &str) -> Self {
        let mut attrs = self.attributes.clone();
        attrs.remove(key);
        Self::new(attrs, self.cursor.clone(), &self.status, self.sequence)
    }

    pub fn advance_sequence(&self) -> Self {
        Self::new(
            self.attributes.clone(),
            self.cursor.clone(),
            &self.status,
            self.sequence + 1,
        )
    }

    pub fn with_status(&self, status: &str) -> Self {
        Self::new(
            self.attributes.clone(),
            self.cursor.clone(),
            status,
            self.sequence,
        )
    }

    pub fn with_cursor(&self, cursor: Option<String>) -> Self {
        Self::new(
            self.attributes.clone(),
            cursor,
            &self.status,
            self.sequence,
        )
    }

    pub fn to_json_value(&self) -> Value {
        let mut map = serde_json::Map::new();
        let mut attrs_obj = serde_json::Map::new();
        for (k, v) in &self.attributes {
            attrs_obj.insert(k.clone(), v.clone());
        }
        map.insert("attributes".to_string(), Value::Object(attrs_obj));
        map.insert(
            "cursor".to_string(),
            match &self.cursor {
                Some(c) => Value::String(c.clone()),
                None => Value::Null,
            },
        );
        map.insert("sequence".to_string(), Value::Number(self.sequence.into()));
        map.insert("status".to_string(), Value::String(self.status.clone()));
        map.insert("state_hash".to_string(), Value::String(self.state_hash.clone()));
        Value::Object(map)
    }

    pub fn evaluate_guard(&self, op: &str, key: &str, operand: &Value) -> bool {
        match op {
            "ALWAYS" => true,
            "EXISTS" => self.attributes.contains_key(key) && !self.attributes[key].is_null(),
            "NOT_EXISTS" => !self.attributes.contains_key(key) || self.attributes[key].is_null(),
            "EQ" => self.attributes.get(key).map_or(false, |v| v == operand),
            "NE" => self.attributes.get(key).map_or(true, |v| v != operand),
            "GT" => self.compare_num(key, operand, |a, b| a > b),
            "GTE" => self.compare_num(key, operand, |a, b| a >= b),
            "LT" => self.compare_num(key, operand, |a, b| a < b),
            "LTE" => self.compare_num(key, operand, |a, b| a <= b),
            _ => false,
        }
    }

    fn compare_num<F>(&self, key: &str, operand: &Value, cmp: F) -> bool
    where
        F: Fn(i64, i64) -> bool,
    {
        if let (Some(a), Some(b)) = (
            self.attributes.get(key).and_then(|v| v.as_i64()),
            operand.as_i64(),
        ) {
            cmp(a, b)
        } else {
            false
        }
    }

    pub fn apply_mutation(&mut self, op: &str, key: &str, operand: &Value) {
        match op {
            "NOOP" => {}
            "SET" => {
                self.attributes.insert(key.to_string(), operand.clone());
            }
            "ADD" => {
                let curr = self.attributes.get(key).and_then(|v| v.as_i64()).unwrap_or(0);
                let delta = operand.as_i64().unwrap_or(0);
                self.attributes
                    .insert(key.to_string(), Value::Number((curr + delta).into()));
            }
            "SUB" => {
                let curr = self.attributes.get(key).and_then(|v| v.as_i64()).unwrap_or(0);
                let delta = operand.as_i64().unwrap_or(0);
                self.attributes
                    .insert(key.to_string(), Value::Number((curr - delta).into()));
            }
            "DELETE" => {
                self.attributes.remove(key);
            }
            _ => {}
        }
        self.state_hash = self.compute_hash();
    }
}
