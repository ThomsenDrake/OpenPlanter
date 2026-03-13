use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::{BTreeMap, BTreeSet};

const SCHEMA_VERSION: &str = "1.0.0";
const ONTOLOGY_NAMESPACE: &str = "openplanter.core";
const ONTOLOGY_VERSION: &str = "2026-03";
const LEGACY_KNOWN_KEYS: &[&str] = &[
    "session_id",
    "saved_at",
    "external_observations",
    "observations",
    "turn_history",
    "loop_metrics",
];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InvestigationState {
    #[serde(default = "default_schema_version")]
    pub schema_version: String,
    #[serde(default)]
    pub session_id: String,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub objective: String,
    #[serde(default)]
    pub ontology: Ontology,
    #[serde(default)]
    pub entities: BTreeMap<String, Value>,
    #[serde(default)]
    pub links: BTreeMap<String, Value>,
    #[serde(default)]
    pub claims: BTreeMap<String, Value>,
    #[serde(default)]
    pub evidence: BTreeMap<String, Value>,
    #[serde(default)]
    pub hypotheses: BTreeMap<String, Value>,
    #[serde(default)]
    pub questions: BTreeMap<String, Value>,
    #[serde(default)]
    pub tasks: BTreeMap<String, Value>,
    #[serde(default)]
    pub actions: BTreeMap<String, Value>,
    #[serde(default)]
    pub provenance_nodes: BTreeMap<String, Value>,
    #[serde(default)]
    pub confidence_profiles: BTreeMap<String, Value>,
    #[serde(default)]
    pub timeline: Vec<Value>,
    #[serde(default)]
    pub indexes: Indexes,
    #[serde(default)]
    pub legacy: LegacyState,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Ontology {
    #[serde(default = "default_ontology_namespace")]
    pub namespace: String,
    #[serde(default = "default_ontology_version")]
    pub version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LegacyState {
    #[serde(default)]
    pub external_observations: Vec<String>,
    #[serde(default)]
    pub turn_history: Vec<Value>,
    #[serde(default)]
    pub loop_metrics: Map<String, Value>,
    #[serde(default)]
    pub extra_fields: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Indexes {
    #[serde(default)]
    pub by_external_ref: BTreeMap<String, Value>,
    #[serde(default)]
    pub by_tag: BTreeMap<String, Value>,
}

impl Default for InvestigationState {
    fn default() -> Self {
        Self::new("")
    }
}

impl Default for Ontology {
    fn default() -> Self {
        Self {
            namespace: default_ontology_namespace(),
            version: default_ontology_version(),
        }
    }
}

impl InvestigationState {
    pub fn new(session_id: &str) -> Self {
        let ts = now();
        Self {
            schema_version: default_schema_version(),
            session_id: session_id.to_string(),
            created_at: ts.clone(),
            updated_at: ts,
            objective: String::new(),
            ontology: Ontology::default(),
            entities: BTreeMap::new(),
            links: BTreeMap::new(),
            claims: BTreeMap::new(),
            evidence: BTreeMap::new(),
            hypotheses: BTreeMap::new(),
            questions: BTreeMap::new(),
            tasks: BTreeMap::new(),
            actions: BTreeMap::new(),
            provenance_nodes: BTreeMap::new(),
            confidence_profiles: BTreeMap::new(),
            timeline: vec![],
            indexes: Indexes::default(),
            legacy: LegacyState::default(),
        }
    }

    pub fn from_legacy_python_state(session_id: &str, legacy_json: &Value) -> Self {
        let mut state = Self::new(session_id);
        let Some(obj) = legacy_json.as_object() else {
            return state;
        };

        if let Some(saved_at) = obj.get("saved_at").and_then(Value::as_str) {
            state.updated_at = saved_at.to_string();
            state.created_at = saved_at.to_string();
        }
        if let Some(session_id) = obj.get("session_id").and_then(Value::as_str) {
            state.session_id = session_id.to_string();
        }
        state.legacy.external_observations = obj
            .get("external_observations")
            .and_then(Value::as_array)
            .map(|items| string_vec(items))
            .unwrap_or_default();
        state.legacy.turn_history = obj
            .get("turn_history")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        state.legacy.loop_metrics = obj
            .get("loop_metrics")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        state.legacy.extra_fields = extra_fields_from_object(obj);
        let observations = state.legacy.external_observations.clone();
        state.merge_legacy_updates(
            &observations,
            Some(&state.legacy.turn_history.clone()),
            Some(&state.legacy.loop_metrics.clone()),
            Some(&state.legacy.extra_fields.clone()),
        );
        state
    }

    pub fn from_legacy_rust_state(session_id: &str, legacy_json: &Value) -> Self {
        let mut state = Self::new(session_id);
        let Some(obj) = legacy_json.as_object() else {
            return state;
        };

        state.legacy.external_observations = obj
            .get("observations")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(|item| item.get("content").and_then(Value::as_str))
                    .map(ToString::to_string)
                    .collect()
            })
            .unwrap_or_default();
        state.legacy.extra_fields = extra_fields_from_object(obj);
        let observations = state.legacy.external_observations.clone();
        state.merge_legacy_updates(
            &observations,
            Some(&state.legacy.turn_history.clone()),
            Some(&state.legacy.loop_metrics.clone()),
            Some(&state.legacy.extra_fields.clone()),
        );
        state
    }

    pub fn legacy_observations(&self) -> Vec<String> {
        if !self.legacy.external_observations.is_empty() {
            return self.legacy.external_observations.clone();
        }

        let mut observations: Vec<(String, String)> = self
            .evidence
            .iter()
            .filter_map(|(evidence_id, record)| {
                if !is_legacy_evidence(evidence_id, record) {
                    return None;
                }
                record
                    .get("content")
                    .and_then(Value::as_str)
                    .map(|content| (evidence_id.clone(), content.to_string()))
            })
            .collect();
        observations.sort_by(|left, right| left.0.cmp(&right.0));
        observations
            .into_iter()
            .map(|(_, content)| content)
            .collect()
    }

    pub fn merge_legacy_updates(
        &mut self,
        observations: &[String],
        turn_history: Option<&[Value]>,
        loop_metrics: Option<&Map<String, Value>>,
        extra_fields: Option<&BTreeMap<String, Value>>,
    ) {
        let ts = now();
        if self.created_at.is_empty() {
            self.created_at = ts.clone();
        }
        self.updated_at = ts.clone();
        self.schema_version = default_schema_version();
        self.legacy.external_observations = observations.to_vec();
        if let Some(turn_history) = turn_history {
            self.legacy.turn_history = turn_history.to_vec();
        }
        if let Some(loop_metrics) = loop_metrics {
            self.legacy.loop_metrics = loop_metrics.clone();
        }
        if let Some(extra_fields) = extra_fields {
            self.legacy.extra_fields = extra_fields.clone();
        }

        for (index, observation) in observations.iter().enumerate() {
            let evidence_id = legacy_evidence_id(index);
            let source_uri = legacy_source_uri(index);
            let created_at = self
                .evidence
                .get(&evidence_id)
                .and_then(|value| value.get("created_at"))
                .and_then(Value::as_str)
                .unwrap_or(ts.as_str())
                .to_string();
            self.evidence.insert(
                evidence_id.clone(),
                serde_json::json!({
                    "id": evidence_id,
                    "evidence_type": "legacy_observation",
                    "content": observation,
                    "source_uri": source_uri,
                    "normalization": {
                        "kind": "legacy_observation",
                        "normalization_version": "legacy-v1",
                    },
                    "provenance_ids": [],
                    "confidence_id": Value::Null,
                    "created_at": created_at,
                    "updated_at": ts,
                }),
            );
            self.indexes
                .by_external_ref
                .insert(source_uri, Value::String(legacy_evidence_id(index)));
        }

        let keep_ids: BTreeSet<String> = (0..observations.len()).map(legacy_evidence_id).collect();
        self.evidence.retain(|evidence_id, record| {
            !is_legacy_evidence(evidence_id, record) || keep_ids.contains(evidence_id)
        });
        self.indexes.by_external_ref.retain(|source_ref, target| {
            if !source_ref.starts_with("state.json#external_observations[") {
                return true;
            }
            target
                .as_str()
                .map(|target| keep_ids.contains(target))
                .unwrap_or(false)
        });
    }

    pub fn to_legacy_python_projection(&self) -> Value {
        let mut projected = Map::new();
        projected.insert(
            "session_id".to_string(),
            Value::String(self.session_id.clone()),
        );
        projected.insert(
            "saved_at".to_string(),
            Value::String(self.updated_at.clone()),
        );
        projected.insert(
            "external_observations".to_string(),
            Value::Array(
                self.legacy_observations()
                    .into_iter()
                    .map(Value::String)
                    .collect(),
            ),
        );
        projected.insert(
            "turn_history".to_string(),
            Value::Array(self.legacy.turn_history.clone()),
        );
        projected.insert(
            "loop_metrics".to_string(),
            Value::Object(self.legacy.loop_metrics.clone()),
        );
        for (key, value) in &self.legacy.extra_fields {
            projected
                .entry(key.clone())
                .or_insert_with(|| value.clone());
        }
        Value::Object(projected)
    }
}

fn default_schema_version() -> String {
    SCHEMA_VERSION.to_string()
}

fn default_ontology_namespace() -> String {
    ONTOLOGY_NAMESPACE.to_string()
}

fn default_ontology_version() -> String {
    ONTOLOGY_VERSION.to_string()
}

fn now() -> String {
    Utc::now().to_rfc3339()
}

fn legacy_evidence_id(index: usize) -> String {
    format!("ev_legacy_{:06}", index + 1)
}

fn legacy_source_uri(index: usize) -> String {
    format!("state.json#external_observations[{index}]")
}

fn string_vec(items: &[Value]) -> Vec<String> {
    items
        .iter()
        .filter_map(Value::as_str)
        .map(ToString::to_string)
        .collect()
}

fn extra_fields_from_object(obj: &Map<String, Value>) -> BTreeMap<String, Value> {
    obj.iter()
        .filter(|(key, _)| !LEGACY_KNOWN_KEYS.contains(&key.as_str()))
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect()
}

fn is_legacy_evidence(evidence_id: &str, record: &Value) -> bool {
    if !evidence_id.starts_with("ev_legacy_") {
        return false;
    }
    record
        .get("normalization")
        .and_then(Value::as_object)
        .and_then(|normalization| normalization.get("kind"))
        .and_then(Value::as_str)
        == Some("legacy_observation")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migrates_legacy_python_state_with_extra_fields() {
        let legacy = serde_json::json!({
            "session_id": "sid",
            "saved_at": "2026-03-13T00:00:00Z",
            "external_observations": ["obs-a", "obs-b"],
            "turn_history": [{"turn_number": 1}],
            "loop_metrics": {"turns": 1},
            "custom_field": "keep-me"
        });

        let state = InvestigationState::from_legacy_python_state("sid", &legacy);
        assert_eq!(state.legacy.external_observations, vec!["obs-a", "obs-b"]);
        assert_eq!(
            state.legacy.extra_fields.get("custom_field"),
            Some(&Value::String("keep-me".to_string()))
        );
        assert_eq!(
            state.evidence["ev_legacy_000001"]["source_uri"],
            Value::String("state.json#external_observations[0]".to_string())
        );
    }

    #[test]
    fn merge_legacy_updates_preserves_non_legacy_fields_and_prunes_old_legacy_entries() {
        let mut state = InvestigationState::new("sid");
        state.questions.insert(
            "q_1".to_string(),
            serde_json::json!({"id": "q_1", "question_text": "keep me"}),
        );
        state.evidence.insert(
            "ev_other".to_string(),
            serde_json::json!({
                "id": "ev_other",
                "content": "keep me",
                "normalization": {"kind": "web_fetch"}
            }),
        );
        state.evidence.insert(
            "ev_legacy_000002".to_string(),
            serde_json::json!({
                "id": "ev_legacy_000002",
                "content": "remove me",
                "normalization": {"kind": "legacy_observation"}
            }),
        );
        let extra_fields = BTreeMap::from([(
            "custom_field".to_string(),
            Value::String("after".to_string()),
        )]);

        state.merge_legacy_updates(&[String::from("fresh")], None, None, Some(&extra_fields));

        assert!(state.questions.contains_key("q_1"));
        assert!(state.evidence.contains_key("ev_other"));
        assert!(!state.evidence.contains_key("ev_legacy_000002"));
        assert_eq!(
            state.evidence["ev_legacy_000001"]["content"],
            Value::String("fresh".to_string())
        );
        assert_eq!(
            state.legacy.extra_fields.get("custom_field"),
            Some(&Value::String("after".to_string()))
        );
    }
}
