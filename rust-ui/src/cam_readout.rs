//! Typed read-only CAM inspection from the authoritative CF3D serializer.
//! A stored motion preview is NEVER a preflight or permission to export NC.
use serde::Deserialize;
use std::collections::HashSet;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MotionState {
    Disabled,
    Stale,
    MissingMotion,
    MotionPresentUnverified,
}
impl MotionState {
    pub fn label(self) -> &'static str {
        match self {
            Self::Disabled => "Disabled",
            Self::Stale => "Recalculate",
            Self::MissingMotion => "Missing motion",
            Self::MotionPresentUnverified => "Motion stored / unverified",
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
pub struct CamStage {
    pub operation_id: String,
    pub strategy: String,
    pub cutter_name: String,
    pub cutter_type: String,
    pub cutter_diameter_mm: f64,
    pub source_item_count: usize,
    pub generated_toolpath_count: usize,
    pub motion_move_count: usize,
    pub state: MotionState,
    pub stale_reason: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct StateCounts {
    pub disabled: usize,
    pub stale: usize,
    pub missing_motion: usize,
    pub motion_present_unverified: usize,
}

#[derive(Clone, Debug, Deserialize)]
pub struct CamReadout {
    pub protocol_version: u32,
    pub source_sha256: String,
    pub project_name: String,
    pub operation_count: usize,
    pub generated_toolpath_count: usize,
    pub fixture_count: usize,
    pub counts: StateCounts,
    pub operations: Vec<CamStage>,
    pub export_allowed_from_rust: bool,
    pub preflight_verified: bool,
    pub notice: String,
}

impl CamReadout {
    pub fn decode(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() > 2_000_000 { return Err("CAM inspection output is too large".into()); }
        let report: Self = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
        report.validate()?;
        Ok(report)
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.protocol_version != 1 || self.export_allowed_from_rust
            || self.preflight_verified {
            return Err("CAM inspection protocol or safety flags are invalid".into());
        }
        if self.source_sha256.len() != 64
            || !self.source_sha256.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()) {
            return Err("CAM source fingerprint is invalid".into());
        }
        if self.operation_count != self.operations.len() || self.operations.len() > 10_000 {
            return Err("CAM operation count mismatch".into());
        }
        if self.project_name.len() > 1024 || self.notice.is_empty() {
            return Err("CAM inspection metadata is invalid".into());
        }
        let mut seen = HashSet::new();
        let mut counts = [0_usize; 4];
        for stage in &self.operations {
            if stage.operation_id.is_empty() || !seen.insert(stage.operation_id.as_str())
                || stage.strategy.is_empty() || stage.cutter_name.is_empty()
                || stage.cutter_type.is_empty()
                || !stage.cutter_diameter_mm.is_finite() || stage.cutter_diameter_mm <= 0.0 {
                return Err("CAM stage identity or cutter is invalid".into());
            }
            let i = match stage.state {
                MotionState::Disabled => 0,
                MotionState::Stale => 1,
                MotionState::MissingMotion => 2,
                MotionState::MotionPresentUnverified => 3,
            };
            counts[i] += 1;
        }
        if counts != [
            self.counts.disabled, self.counts.stale,
            self.counts.missing_motion, self.counts.motion_present_unverified,
        ] {
            return Err("CAM readiness state totals do not match operations".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stale_readout_is_informational_only() {
        let raw = serde_json::json!({
            "protocol_version": 1,
            "source_sha256": "a".repeat(64),
            "project_name": "Shop",
            "operation_count": 1,
            "generated_toolpath_count": 0,
            "fixture_count": 2,
            "counts": { "disabled": 0, "stale": 1,
                "missing_motion": 0, "motion_present_unverified": 0 },
            "operations": [{
                "operation_id": "persistent-1", "strategy": "Profile",
                "cutter_name": "Quarter-inch", "cutter_type": "flat_end_mill",
                "cutter_diameter_mm": 6.35, "source_item_count": 1,
                "generated_toolpath_count": 0, "motion_move_count": 0,
                "state": "stale", "stale_reason": "Source moved"
            }],
            "export_allowed_from_rust": false,
            "preflight_verified": false,
            "notice": "Recalculate before machining"
        });
        let data = serde_json::to_vec(&raw).unwrap();
        let parsed = CamReadout::decode(&data).unwrap();
        assert_eq!(parsed.operations[0].state, MotionState::Stale);
        assert_eq!(parsed.counts.stale, 1);
    }

    #[test]
    fn refuses_false_authorization_and_inconsistent_counts() {
        let raw = serde_json::json!({
            "protocol_version": 1, "source_sha256": "b".repeat(64),
            "project_name": "Shop", "operation_count": 0,
            "generated_toolpath_count": 0, "fixture_count": 0,
            "counts": { "disabled": 0, "stale": 1,
                "missing_motion": 0, "motion_present_unverified": 0 },
            "operations": [], "export_allowed_from_rust": true,
            "preflight_verified": false, "notice": "Inspect only"
        });
        let data = serde_json::to_vec(&raw).unwrap();
        assert!(CamReadout::decode(&data).is_err());
        let mut corrected = raw;
        corrected["export_allowed_from_rust"] = serde_json::json!(false);
        assert!(CamReadout::decode(&serde_json::to_vec(&corrected).unwrap()).is_err());
    }
}
