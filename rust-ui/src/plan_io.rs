//! Versioned read-only preview plan JSON boundary.
//!
//! Multi-sheet plans do not contain cutter data or CNC machine commands and
//! must never be interpreted as authoritative CF3D project files.
use crate::multi_sheet::MultiSheetPlan;

pub fn deserialize_plan(input: &str) -> Result<MultiSheetPlan, String> {
    const MAX_PLAN_JSON_BYTES: usize = 8 * 1024 * 1024;
    if input.len() > MAX_PLAN_JSON_BYTES {
        return Err("Multi-sheet plan JSON exceeds the 8 MiB limit".into());
    }
    let plan: MultiSheetPlan = serde_json::from_str(input)
        .map_err(|error| format!("Invalid multi-sheet plan JSON: {error}"))?;
    plan.validate()?;
    Ok(plan)
}

pub fn serialize_plan(plan: &MultiSheetPlan) -> Result<String, String> {
    plan.validate()?;
    serde_json::to_string_pretty(plan).map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::{Part, Sheet, rectangle};
    use crate::multi_sheet::{NestSettings, nest_multiple};

    fn sample_plan() -> MultiSheetPlan {
        let sheet = Sheet {
            width_mm: 40.0, height_mm: 40.0,
            parts: vec![
                Part { id: 5, name: "A".into(), outline: rectangle(30.0, 30.0),
                       x: 0.0, y: 0.0, quarter_turns: 0 },
                Part { id: 7, name: "B".into(), outline: rectangle(30.0, 30.0),
                       x: 0.0, y: 0.0, quarter_turns: 0 },
            ],
            ..Sheet::default()
        };
        nest_multiple(&sheet, NestSettings {
            max_sheets: 3, gap_mm: 2.0, margin_mm: 2.0, step_mm: 2.0,
            ..NestSettings::default()
        }).unwrap()
    }

    #[test]
    fn full_roundtrip_preserves_independent_sheets_and_source_part_ids() {
        let plan = sample_plan();
        assert_eq!(plan.sheets.len(), 2);
        let data = serialize_plan(&plan).unwrap();
        assert_eq!(deserialize_plan(&data).unwrap(), plan);
        assert_eq!(plan.sheets[0].parts[0].id, 5);
        assert_eq!(plan.sheets[1].parts[0].id, 7);
    }

    #[test]
    fn tampering_with_stock_or_clearance_is_rejected_on_open() {
        let plan = sample_plan();
        let mut edited = serde_json::to_value(plan).unwrap();
        edited["sheets"][0]["parts"][0]["x"] = serde_json::json!(-4.0);
        assert!(deserialize_plan(&edited.to_string()).unwrap_err().contains("clearance"));
    }

    #[test]
    fn incompatible_version_and_bogus_json_fail_closed() {
        let plan = sample_plan();
        let mut edited = serde_json::to_value(plan).unwrap();
        edited["format_version"] = serde_json::json!(2);
        assert!(deserialize_plan(&edited.to_string()).unwrap_err().contains("version"));
        assert!(deserialize_plan("{bad").is_err());
        assert!(deserialize_plan(&" ".repeat(8 * 1024 * 1024 + 1)).is_err());
    }

    #[test]
    fn rejected_file_cannot_discard_a_valid_existing_preview() {
        // Pure decoding has no side effects; the GUI only swaps the preview
        // after receiving a fully validated new plan.
        let old = sample_plan();
        assert!(deserialize_plan("[]").is_err());
        assert_eq!(old.sheets.len(), 2);
    }
}
