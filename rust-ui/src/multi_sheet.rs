//! Bounded, deterministic multi-sheet polygon packing for Rust Studio.
//!
//! Preview plans are independent from the source layout and cannot authorize
//! CNC cutting. This is a first-fit heuristic, not optimal stock utilization.
use crate::geometry::{Part, Sheet, area};
use crate::nesting::valid_placement;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

pub const MAX_PLAN_SHEETS: usize = 32;
const MAX_CANDIDATES_PER_ROTATION: usize = 12_000;

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct NestSettings {
    pub gap_mm: f64,
    pub margin_mm: f64,
    pub step_mm: f64,
    pub allow_quarter_turns: bool,
    pub max_sheets: usize,
}

impl Default for NestSettings {
    fn default() -> Self {
        Self { gap_mm: 3.0, margin_mm: 5.0, step_mm: 3.0,
            allow_quarter_turns: true, max_sheets: 8 }
    }
}

impl NestSettings {
    pub fn validate(&self) -> Result<(), String> {
        if !self.gap_mm.is_finite() || !self.margin_mm.is_finite()
            || !self.step_mm.is_finite() || self.gap_mm < 0.0
            || self.margin_mm < 0.0 || !(0.5..=50.0).contains(&self.step_mm)
            || !(1..=MAX_PLAN_SHEETS).contains(&self.max_sheets) {
            return Err("Invalid nesting settings: require finite nonnegative gap/margin, step 0.5–50 mm, 1–32 sheets".into());
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct MultiSheetPlan {
    pub format_version: u32,
    pub source_name: String,
    pub settings: NestSettings,
    pub sheets: Vec<Sheet>,
}

impl MultiSheetPlan {
    pub fn validate(&self) -> Result<(), String> {
        if self.format_version != 1 {
            return Err("Unsupported multi-sheet plan version".into());
        }
        self.settings.validate()?;
        if self.sheets.is_empty() || self.sheets.len() > self.settings.max_sheets {
            return Err("Plan sheet count is invalid".into());
        }
        let mut ids = HashSet::new();
        let first = &self.sheets[0];
        for sheet in &self.sheets {
            sheet.validate()?;
            if sheet.width_mm != first.width_mm || sheet.height_mm != first.height_mm {
                return Err("Sheets within a plan must have the same stock dimensions".into());
            }
            for (index, part) in sheet.parts.iter().enumerate() {
                if !ids.insert(part.id) {
                    return Err("A part ID occurs on more than one sheet".into());
                }
                if !valid_placement(
                    part, &sheet.parts[..index], sheet,
                    self.settings.gap_mm, self.settings.margin_mm,
                ) {
                    return Err(format!("Invalid stock/clearance on sheet '{}'", sheet.name));
                }
            }
        }
        Ok(())
    }

    pub fn utilization_percent(&self, index: usize) -> Option<f64> {
        let sheet = self.sheets.get(index)?;
        let stock_area = sheet.width_mm * sheet.height_mm;
        Some(100.0 * sheet.parts.iter().map(|p| area(&p.outline)).sum::<f64>() / stock_area)
    }
}

fn placement(
    template: &Part,
    placed: &[Part],
    stock: &Sheet,
    settings: NestSettings,
) -> Result<Option<Part>, String> {
    let rotations = if settings.allow_quarter_turns { 4 } else { 1 };
    for rotation in 0..rotations {
        let mut candidate = template.clone();
        candidate.quarter_turns = if settings.allow_quarter_turns {
            rotation
        } else {
            template.quarter_turns
        };
        let size = candidate.size();
        let max_x = stock.width_mm - settings.margin_mm - size[0];
        let max_y = stock.height_mm - settings.margin_mm - size[1];
        if max_x < settings.margin_mm - 1e-8 || max_y < settings.margin_mm - 1e-8 {
            continue;
        }
        let nx = ((max_x - settings.margin_mm) / settings.step_mm).floor() as usize;
        let ny = ((max_y - settings.margin_mm) / settings.step_mm).floor() as usize;
        if (nx + 2).saturating_mul(ny + 2) > MAX_CANDIDATES_PER_ROTATION {
            return Err("Packing search too dense. Increase the search step or reduce stock size.".into());
        }
        // Check both the regular grid and exact last stock boundaries.
        for row in 0..=ny + 1 {
            let y = if row == ny + 1 {
                max_y
            } else {
                settings.margin_mm + row as f64 * settings.step_mm
            };
            for column in 0..=nx + 1 {
                let x = if column == nx + 1 {
                    max_x
                } else {
                    settings.margin_mm + column as f64 * settings.step_mm
                };
                candidate.x = x;
                candidate.y = y;
                if valid_placement(&candidate, placed, stock, settings.gap_mm, settings.margin_mm) {
                    return Ok(Some(candidate));
                }
            }
        }
    }
    Ok(None)
}

/// Lay out source parts across bounded sheets; no mutations if packing fails.
pub fn nest_multiple(source: &Sheet, settings: NestSettings) -> Result<MultiSheetPlan, String> {
    source.validate()?;
    settings.validate()?;
    if source.parts.is_empty() {
        return Err("Add vector parts before multi-sheet nesting".into());
    }
    let mut parts = source.parts.clone();
    parts.sort_by(|a, b| area(&b.outline).total_cmp(&area(&a.outline))
        .then_with(|| a.id.cmp(&b.id)));
    let mut sheets = Vec::<Sheet>::new();
    for part in parts {
        let mut packed = false;
        for sheet in &mut sheets {
            if let Some(next) = placement(&part, &sheet.parts, sheet, settings)? {
                sheet.parts.push(next);
                packed = true;
                break;
            }
        }
        if packed { continue; }
        if sheets.len() == settings.max_sheets {
            return Err(format!(
                "Unable to fit all parts within {} sheets; no changes were applied.",
                settings.max_sheets,
            ));
        }
        let mut new_sheet = Sheet {
            format_version: source.format_version,
            name: format!("{} — Sheet {}", source.name, sheets.len() + 1),
            width_mm: source.width_mm,
            height_mm: source.height_mm,
            parts: Vec::new(),
        };
        let placed = placement(&part, &[], &new_sheet, settings)?
            .ok_or_else(|| format!("Part '{}' cannot fit on an empty sheet", part.name))?;
        new_sheet.parts.push(placed);
        sheets.push(new_sheet);
    }
    let output = MultiSheetPlan {
        format_version: 1,
        source_name: source.name.clone(),
        settings,
        sheets,
    };
    output.validate()?;
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::{rectangle, star};
    fn part(id: u64, outline: Vec<[f64; 2]>) -> Part {
        Part { id, name: format!("Part {id}"), outline, x: 0.0, y: 0.0, quarter_turns: 0 }
    }
    fn sample() -> Sheet {
        Sheet {
            width_mm: 44.0, height_mm: 28.0,
            parts: (1..=5).map(|id| part(id, rectangle(20.0, 20.0))).collect(),
            ..Sheet::default()
        }
    }
    #[test]
    fn splits_part_sets_and_preserves_all_unique_ids() {
        let source = sample();
        let original = source.clone();
        let cfg = NestSettings { max_sheets: 8, gap_mm: 2.0, margin_mm: 2.0, step_mm: 2.0, ..NestSettings::default() };
        let plan = nest_multiple(&source, cfg).unwrap();
        assert_eq!(plan.sheets.len(), 3);
        assert_eq!(plan.sheets.iter().map(|s| s.parts.len()).sum::<usize>(), 5);
        assert_eq!(plan, nest_multiple(&source, cfg).unwrap());
        plan.validate().unwrap();
        assert_eq!(source, original);
        assert!(plan.sheets.iter().all(|sheet| sheet.parts.iter().all(|p| {
            p.x >= cfg.margin_mm && p.y >= cfg.margin_mm
        })));
    }
    #[test]
    fn respects_sheet_limit_and_is_atomic() {
        let source = sample();
        let original = source.clone();
        let cfg = NestSettings { max_sheets: 1, gap_mm: 2.0, margin_mm: 2.0, step_mm: 2.0, ..NestSettings::default() };
        assert!(nest_multiple(&source, cfg).unwrap_err().contains("Unable to fit"));
        assert_eq!(source, original);
    }
    #[test]
    fn refuses_single_oversize_item() {
        let source = Sheet {
            width_mm: 20.0, height_mm: 20.0,
            parts: vec![part(1, rectangle(50.0, 10.0))],
            ..Sheet::default()
        };
        assert!(nest_multiple(&source, NestSettings::default()).unwrap_err().contains("cannot fit"));
    }
    #[test]
    fn rotation_setting_preserves_existing_orientation_when_locked() {
        let mut source = Sheet {
            width_mm: 38.0, height_mm: 24.0,
            parts: vec![part(1, rectangle(20.0, 30.0))],
            ..Sheet::default()
        };
        let mut cfg = NestSettings { margin_mm: 1.0, step_mm: 2.0, ..NestSettings::default() };
        cfg.allow_quarter_turns = false;
        assert!(nest_multiple(&source, cfg).is_err());
        cfg.allow_quarter_turns = true;
        let plan = nest_multiple(&source, cfg).unwrap();
        assert_eq!(plan.sheets[0].parts[0].quarter_turns % 2, 1);
        source.parts[0].quarter_turns = 1;
        cfg.allow_quarter_turns = false;
        assert_eq!(nest_multiple(&source, cfg).unwrap().sheets[0].parts[0].quarter_turns, 1);
    }
    #[test]
    fn supports_concave_profiles_with_clearance_checks() {
        let source = Sheet {
            width_mm: 60.0, height_mm: 50.0,
            parts: vec![part(1, star(5, 13.0, 6.0)), part(2, rectangle(15.0, 12.0))],
            ..Sheet::default()
        };
        let result = nest_multiple(&source, NestSettings { gap_mm: 2.0, step_mm: 2.0, ..NestSettings::default() }).unwrap();
        result.validate().unwrap();
    }
    #[test]
    fn plan_serialization_is_versioned_and_rejects_conflicts() {
        let plan = nest_multiple(&sample(), NestSettings {
            gap_mm: 2.0, margin_mm: 2.0, step_mm: 2.0, ..NestSettings::default()
        }).unwrap();
        let json = serde_json::to_string(&plan).unwrap();
        let loaded: MultiSheetPlan = serde_json::from_str(&json).unwrap();
        assert_eq!(loaded, plan);
        let mut corrupt = loaded;
        corrupt.sheets[1].parts[0].id = corrupt.sheets[0].parts[0].id;
        assert!(corrupt.validate().is_err());
    }
    #[test]
    fn search_rejects_unbounded_geometry() {
        let source = Sheet {
            width_mm: 10_000.0, height_mm: 10_000.0,
            parts: vec![part(1, rectangle(10.0, 10.0))],
            ..Sheet::default()
        };
        assert!(nest_multiple(&source, NestSettings {
            step_mm: 0.5, ..NestSettings::default()
        }).unwrap_err().contains("too dense"));
    }
}
