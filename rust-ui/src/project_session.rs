//! Unified, loss-aware CF3D inspection session for the native desktop.
//!
//! Python owns project deserialization and CAM decisions. This Rust model
//! validates the read-only session and keeps vector, fixture and CAM data
//! pinned to the same source digest before updating any UI state.
use crate::cam_readout::CamReadout;
use crate::geometry::Sheet;
use crate::source_placement::SourcePlacement;
use serde::Deserialize;
use serde_json::Value;
use std::collections::HashSet;

const MAX_BYTES: usize = 8_000_000;

#[derive(Clone, Debug, Deserialize)]
pub struct StockInfo {
    pub width_mm: f64,
    pub height_mm: f64,
    pub thickness_mm: f64,
    pub xy_zero: String,
}
#[derive(Clone, Debug, Deserialize)]
pub struct FixtureInfo {
    pub name: String,
    pub x_min_mm: f64,
    pub x_max_mm: f64,
    pub y_min_mm: f64,
    pub y_max_mm: f64,
    pub top_z_mm: f64,
    pub clearance_mm: f64,
}
#[derive(Clone, Debug, Deserialize)]
pub struct ItemInfo {
    pub item_id: String,
    pub name: String,
    pub kind: String,
    pub visible: bool,
    pub locked: bool,
    pub has_mesh: bool,
    pub has_vector: bool,
}
#[derive(Clone, Debug, Deserialize)]
pub struct ProjectSession {
    pub session_version: u32,
    pub source_sha256: String,
    pub source_was_read_only: bool,
    pub export_allowed_from_rust: bool,
    pub preflight_verified: bool,
    pub stock: StockInfo,
    pub layout: Value,
    pub cam: CamReadout,
    pub fixtures: Vec<FixtureInfo>,
    pub items: Vec<ItemInfo>,
    pub material_name: String,
}
impl ProjectSession {
    /// Decode ALL sections before replacing the current GUI document.
    pub fn decode(
        bytes: &[u8], source_path: &str,
    ) -> Result<(Self, Sheet, SourcePlacement), String> {
        if bytes.len() > MAX_BYTES {
            return Err("Native CF3D session exceeds 8 MB".into());
        }
        let session: Self = serde_json::from_slice(bytes)
            .map_err(|e| format!("Invalid native CF3D session: {e}"))?;
        let layout: Sheet = serde_json::from_value(session.layout.clone())
            .map_err(|e| format!("Cannot decode source vector layout: {e}"))?;
        session.validate(&layout)?;
        let link = SourcePlacement::from_snapshot(
            &session.layout, &layout, source_path,
        )?;
        for id in link.uuid_by_part_id.values() {
            if !session.items.iter().any(|item| &item.item_id == id
                && item.has_vector && item.has_mesh && item.visible) {
                return Err("Source vector identity missing from complete project inventory".into());
            }
        }
        Ok((session, layout, link))
    }

    pub fn validate(&self, layout: &Sheet) -> Result<(), String> {
        if self.session_version != 1 || !self.source_was_read_only
            || self.export_allowed_from_rust || self.preflight_verified {
            return Err("Unsupported or unsafe native CF3D session policy".into());
        }
        self.cam.validate()?;
        if self.source_sha256 != self.cam.source_sha256
            || self.layout.get("source_sha256").and_then(Value::as_str)
                != Some(self.source_sha256.as_str())
            || self.layout.get("source_was_read_only").and_then(Value::as_bool) != Some(true)
            || self.layout.get("excluded_cam_and_fixtures").and_then(Value::as_bool) != Some(true) {
            return Err("CF3D vector/CAM sections do not share the same source digest and read policy".into());
        }
        layout.validate()?;
        if !self.stock.width_mm.is_finite() || !self.stock.height_mm.is_finite()
            || !self.stock.thickness_mm.is_finite()
            || self.stock.xy_zero != "bottom_left"
            || self.stock.thickness_mm <= 0.0 || self.stock.thickness_mm > 100_000.0
            || layout.width_mm != self.stock.width_mm
            || layout.height_mm != self.stock.height_mm {
            return Err("CF3D stock dimensions/origin disagree with the Rust layout".into());
        }
        if self.fixtures.len() > 2_048 || self.items.len() > 10_000
            || self.material_name.len() > 256 {
            return Err("Native project item/fixture inventory exceeds safe bounds".into());
        }
        let mut unique = HashSet::new();
        for item in &self.items {
            if item.item_id.is_empty() || !unique.insert(item.item_id.as_str())
                || item.name.len() > 256 || item.kind.len() > 128 {
                return Err("Invalid or repeated source project item ID".into());
            }
        }
        for fixture in &self.fixtures {
            if fixture.name.is_empty() || fixture.name.len() > 256
                || [
                    fixture.x_min_mm, fixture.x_max_mm,
                    fixture.y_min_mm, fixture.y_max_mm,
                    fixture.top_z_mm, fixture.clearance_mm,
                ].into_iter().any(|v| !v.is_finite() || v.abs() > 100_000.0)
                || fixture.x_max_mm <= fixture.x_min_mm
                || fixture.y_max_mm <= fixture.y_min_mm
                || fixture.clearance_mm < 0.0 {
                return Err("Invalid stock-relative fixture keep-out".into());
            }
        }
        if self.cam.fixture_count != self.fixtures.len() {
            return Err("CAM and project fixture counts disagree".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn fixture() -> Value {
        json!({
            "name":"Left fence", "x_min_mm":-5.0, "x_max_mm":0.0,
            "y_min_mm":0.0, "y_max_mm":100.0,
            "top_z_mm":4.0, "clearance_mm":2.0
        })
    }
    fn sample() -> Value {
        json!({
            "session_version":1, "source_sha256":"a".repeat(64),
            "source_was_read_only":true,
            "export_allowed_from_rust":false, "preflight_verified":false,
            "stock":{"width_mm":300.0,"height_mm":200.0,
                "thickness_mm":19.0, "xy_zero":"bottom_left"},
            "layout":{
                "format_version":1,"name":"Read-only snapshot",
                "width_mm":300.0,"height_mm":200.0,"parts":[{
                    "id":1,"source_item_id":"stable-uuid-1","name":"Cutout",
                    "outline":[[0.0,0.0],[10.0,0.0],[10.0,8.0],[0.0,8.0]],
                    "x":15.0,"y":9.0,"quarter_turns":0
                }],"source_sha256":"a".repeat(64),
                "skipped_items":1,"source_was_read_only":true,
                "excluded_cam_and_fixtures":true
            },
            "cam":{
                "protocol_version":1,"source_sha256":"a".repeat(64),
                "project_name":"Job", "operation_count":0,
                "generated_toolpath_count":0,"fixture_count":1,
                "counts":{"disabled":0,"stale":0,"missing_motion":0,
                    "motion_present_unverified":0},
                "operations":[],"export_allowed_from_rust":false,
                "preflight_verified":false,"notice":"Inspected only"
            },
            "fixtures":[fixture()],
            "items":[
                {"item_id":"stable-uuid-1","name":"Cutout","kind":"pen",
                    "visible":true,"locked":false,"has_mesh":true,"has_vector":true},
                {"item_id":"mesh-2","name":"Raised model","kind":"mesh",
                    "visible":true,"locked":false,"has_mesh":true,"has_vector":false}
            ],
            "material_name":"Maple"
        })
    }
    fn load(value: Value) -> Result<(ProjectSession, Sheet, SourcePlacement), String> {
        ProjectSession::decode(&serde_json::to_vec(&value).unwrap(), "stock.cf3d")
    }
    #[test]
    fn opens_atomic_inventory_and_source_identity() {
        let (data, sheet, link) = load(sample()).unwrap();
        assert_eq!(data.items.len(), 2);
        assert_eq!(sheet.parts.len(), 1);
        assert_eq!(data.stock.thickness_mm, 19.0);
        assert_eq!(data.fixtures[0].top_z_mm, 4.0);
        assert_eq!(link.uuid_by_part_id.get(&1).unwrap(), "stable-uuid-1");
        assert_eq!(data.cam.fixture_count, 1);
    }
    #[test]
    fn refuses_mismatched_hashes_and_mutable_or_authorized_sessions() {
        for change in 0..5 {
            let mut s = sample();
            match change {
                0 => s["cam"]["source_sha256"] = json!("b".repeat(64)),
                1 => s["layout"]["source_sha256"] = json!("c".repeat(64)),
                2 => s["export_allowed_from_rust"] = json!(true),
                3 => s["preflight_verified"] = json!(true),
                _ => s["source_was_read_only"] = json!(false),
            }
            assert!(load(s).is_err());
        }
    }
    #[test]
    fn refuses_missing_item_identity_invalid_stock_and_fixture_fields() {
        let mut s = sample();
        s["items"][0]["item_id"] = json!("other-id");
        assert!(load(s).is_err());
        let mut s = sample();
        s["stock"]["thickness_mm"] = json!(0.0);
        assert!(load(s).is_err());
        let mut s = sample();
        s["fixtures"][0]["clearance_mm"] = json!(-1.0);
        assert!(load(s).is_err());
        let mut s = sample();
        s["cam"]["fixture_count"] = json!(0);
        assert!(load(s).is_err());
    }
    #[test]
    fn rejects_bad_output_and_extra_inventory() {
        assert!(ProjectSession::decode(b"{", "job.cf3d").is_err());
        assert!(ProjectSession::decode(&vec![b'x'; MAX_BYTES + 1], "job.cf3d").is_err());
        let mut s = sample();
        s["items"][1]["item_id"] = json!("stable-uuid-1");
        assert!(load(s).is_err());
    }
}
