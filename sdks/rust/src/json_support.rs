// Copyright 2026 ACP Project
// Licensed under the Apache License, Version 2.0
// See LICENSE file for details.

use serde::Serialize;
use serde::de::DeserializeOwned;
use serde_json::{Map, Value};

use crate::errors::{AcpError, AcpResult};

pub type JsonMap = Map<String, Value>;

pub fn to_json<T: Serialize>(value: &T) -> AcpResult<String> {
    serde_json::to_string(value).map_err(AcpError::from)
}

pub fn from_json<T: DeserializeOwned>(value: &str) -> AcpResult<T> {
    serde_json::from_str(value).map_err(AcpError::from)
}

pub fn to_value<T: Serialize>(value: &T) -> AcpResult<Value> {
    serde_json::to_value(value).map_err(AcpError::from)
}

pub fn to_map<T: Serialize>(value: &T) -> AcpResult<JsonMap> {
    match to_value(value)? {
        Value::Object(map) => Ok(map),
        _ => Err(AcpError::Validation("expected JSON object".to_string())),
    }
}

pub fn value_to_map(value: Value) -> AcpResult<JsonMap> {
    match value {
        Value::Object(map) => Ok(map),
        _ => Err(AcpError::Validation("expected JSON object".to_string())),
    }
}

pub fn map_from_json(value: &str) -> AcpResult<JsonMap> {
    match serde_json::from_str::<Value>(value)? {
        Value::Object(map) => Ok(map),
        _ => Err(AcpError::Validation(
            "unable to parse JSON object".to_string(),
        )),
    }
}

pub fn convert<T: DeserializeOwned>(value: &Value) -> AcpResult<T> {
    serde_json::from_value(value.clone()).map_err(AcpError::from)
}

pub fn canonical_json_string(value: &Value) -> AcpResult<String> {
    let normalized = normalize_json(value);
    serde_json::to_string(&normalized).map_err(AcpError::from)
}

pub fn canonical_json_bytes(value: &Value) -> AcpResult<Vec<u8>> {
    Ok(canonical_json_string(value)?.into_bytes())
}

fn normalize_json(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut keys = map.keys().cloned().collect::<Vec<_>>();
            keys.sort();
            let mut out = JsonMap::new();
            for key in keys {
                if let Some(item) = map.get(&key) {
                    out.insert(key, normalize_json(item));
                }
            }
            Value::Object(out)
        }
        Value::Array(items) => Value::Array(items.iter().map(normalize_json).collect()),
        _ => value.clone(),
    }
}
