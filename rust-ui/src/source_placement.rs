//! Source-linked, placement-only CF3D edits for the native Rust workspace.
//!
//! Never serialize Rust layout geometry back into CF3D: retained analytic
//! paths, mesh assets and all cutter-facing structures stay in the trusted
//! Python serializer. Only checked XY displacements are sent to its service.
use crate::geometry::Sheet;
use serde_json::{Value, json};
use std::collections::{BTreeMap, HashSet};

#[derive(Clone, Debug)]
pub struct SourcePlacement {
    pub source_path: String,
    pub source_sha256: String,
    pub baseline: Sheet,
    pub uuid_by_part_id: BTreeMap<u64, String>,
}

impl SourcePlacement {
    pub fn from_snapshot(
        value: &Value, baseline: &Sheet, source_path: &str,
    ) -> Result<Self, String> {
        baseline.validate()?;
        let sha = value.get("source_sha256").and_then(Value::as_str)
            .ok_or("Read-only snapshot has no source SHA-256")?;
        if sha.len() != 64 || !sha.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()) {
            return Err("Invalid CF3D source SHA-256".into());
        }
        let raw = value.get("parts").and_then(Value::as_array)
            .ok_or("Read-only CF3D vector snapshot has no parts")?;
        if raw.len() != baseline.parts.len() {
            return Err("Snapshot source parts do not match Rust vector geometry".into());
        }
        let mut links = BTreeMap::new();
        let mut uuids = HashSet::new();
        for entry in raw {
            let id = entry.get("id").and_then(Value::as_u64)
                .ok_or("CF3D part has no stable local reference")?;
            let uuid = entry.get("source_item_id").and_then(Value::as_str)
                .ok_or("CF3D part has no original project UUID")?;
            if uuid.is_empty() || !uuids.insert(uuid.to_owned())
                || links.insert(id, uuid.to_owned()).is_some() {
                return Err("Repeated or invalid CF3D item identity".into());
            }
        }
        if !baseline.parts.iter().all(|p| links.contains_key(&p.id)) {
            return Err("Snapshot part identities cannot be verified".into());
        }
        Ok(Self {
            source_path: source_path.to_owned(),
            source_sha256: sha.to_owned(),
            baseline: baseline.clone(),
            uuid_by_part_id: links,
        })
    }

    /// Build a transaction only if all other vector properties are untouched.
    pub fn request(&self, edited: &Sheet) -> Result<Value, String> {
        self.baseline.validate()?;
        edited.validate()?;
        if edited.width_mm != self.baseline.width_mm
            || edited.height_mm != self.baseline.height_mm
            || edited.parts.len() != self.baseline.parts.len() {
            return Err("Changing stock or adding/removing geometry is not supported for CF3D placement".into());
        }
        let mut edits = Vec::new();
        for prior in &self.baseline.parts {
            let present = edited.parts.iter().find(|p| p.id == prior.id)
                .ok_or("An original CF3D vector was removed or its ID changed")?;
            if present.name != prior.name || present.outline != prior.outline
                || present.quarter_turns != prior.quarter_turns {
                return Err("Only XY translation is supported; vector shapes, names and rotation must match the imported CF3D".into());
            }
            let dx = present.x - prior.x;
            let dy = present.y - prior.y;
            if !dx.is_finite() || !dy.is_finite()
                || dx.abs() > 100_000.0 || dy.abs() > 100_000.0 {
                return Err("CF3D placement change exceeds the safe XY range".into());
            }
            if dx != 0.0 || dy != 0.0 {
                let uuid = self.uuid_by_part_id.get(&prior.id)
                    .ok_or("Missing original CF3D item UUID")?;
                edits.push(json!({
                    "item_id": uuid,
                    "delta_x_mm": dx,
                    "delta_y_mm": dy,
                }));
            }
        }
        if edits.is_empty() {
            return Err("Move at least one imported vector before saving a new CF3D".into());
        }
        Ok(json!({
            "protocol_version": 1,
            "source_sha256": self.source_sha256,
            "edits": edits,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::{Part, rectangle};

    fn source() -> (SourcePlacement, Sheet) {
        let baseline = Sheet { parts: vec![
            Part { id: 2, name: "Panel".into(), outline: rectangle(15.0, 8.0),
                x: 10.0, y: 20.0, quarter_turns: 0 },
            Part { id: 5, name: "Frame".into(), outline: rectangle(7.0, 8.0),
                x: 45.0, y: 20.0, quarter_turns: 0 },
        ], ..Sheet::default() };
        let raw = json!({
            "source_sha256": "a".repeat(64),
            "parts": [
                { "id": 2, "source_item_id": "persistent-uuid-2" },
                { "id": 5, "source_item_id": "persistent-uuid-5" }
            ]
        });
        let link = SourcePlacement::from_snapshot(&raw, &baseline, "shop.cf3d").unwrap();
        (link, baseline)
    }

    #[test]
    fn checked_movement_preserves_uuids_and_absolute_source_precondition() {
        let (link, mut edited) = source();
        edited.parts[0].x += 3.0;
        edited.parts[1].y -= 1.0;
        let report = link.request(&edited).unwrap();
        assert_eq!(report["source_sha256"], "a".repeat(64));
        assert_eq!(report["edits"][0]["item_id"], "persistent-uuid-2");
        assert_eq!(report["edits"][0]["delta_x_mm"], 3.0);
        assert_eq!(report["edits"][1]["item_id"], "persistent-uuid-5");
        assert_eq!(report["edits"][1]["delta_y_mm"], -1.0);
    }

    #[test]
    fn refuses_added_removed_or_rotated_vector_geometry() {
        let (link, mut edited) = source();
        edited.parts[0].quarter_turns = 1;
        assert!(link.request(&edited).is_err());
        edited.parts[0].quarter_turns = 0;
        edited.parts[1].name.push_str(" renamed");
        assert!(link.request(&edited).is_err());
        edited.parts.pop();
        assert!(link.request(&edited).is_err());
    }

    #[test]
    fn rejects_empty_no_op_and_changed_stock() {
        let (link, mut edited) = source();
        assert!(link.request(&edited).is_err());
        edited.width_mm += 3.0;
        assert!(link.request(&edited).is_err());
    }

    #[test]
    fn rejects_missing_source_fingerprint_or_duplicate_uuids() {
        let (link, original) = source();
        let raw = json!({
            "source_sha256": "not-a-hash",
            "parts": [
                { "id": 2, "source_item_id": "same" },
                { "id": 5, "source_item_id": "same" }
            ]
        });
        assert!(SourcePlacement::from_snapshot(&raw, &original, "file.cf3d").is_err());
        let mut raw = raw;
        raw["source_sha256"] = json!("b".repeat(64));
        assert!(SourcePlacement::from_snapshot(&raw, &original, "file.cf3d").is_err());
        assert_eq!(link.baseline.parts.len(), 2);
    }
}
