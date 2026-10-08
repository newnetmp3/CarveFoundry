//! Deterministic polygon-aware first-fit sheet nesting.
//!
//! Works on actual closed polygon outlines, including concave stars/L-shapes.
//! This is a bounded heuristic, NOT globally optimal true-shape nesting.
//! The calculation never posts G-code or overrides existing CAM preflight.
use crate::geometry::{Part, Sheet, area, bounds};

const EPS: f64 = 1e-8;

fn cross(a: [f64; 2], b: [f64; 2], c: [f64; 2]) -> f64 {
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}
fn on_segment(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> bool {
    cross(a, b, p).abs() <= EPS
        && p[0] >= a[0].min(b[0]) - EPS
        && p[0] <= a[0].max(b[0]) + EPS
        && p[1] >= a[1].min(b[1]) - EPS
        && p[1] <= a[1].max(b[1]) + EPS
}
fn edges_cross(a: [f64; 2], b: [f64; 2], c: [f64; 2], d: [f64; 2]) -> bool {
    let u = cross(a, b, c);
    let v = cross(a, b, d);
    let w = cross(c, d, a);
    let x = cross(c, d, b);
    (u * v < -EPS && w * x < -EPS)
        || (u.abs() <= EPS && on_segment(c, a, b))
        || (v.abs() <= EPS && on_segment(d, a, b))
        || (w.abs() <= EPS && on_segment(a, c, d))
        || (x.abs() <= EPS && on_segment(b, c, d))
}
pub fn contains(poly: &[[f64; 2]], p: [f64; 2]) -> bool {
    let mut inside = false;
    for i in 0..poly.len() {
        let a = poly[i];
        let b = poly[(i + 1) % poly.len()];
        if on_segment(p, a, b) {
            return true;
        }
        if (a[1] > p[1]) != (b[1] > p[1]) {
            let crossing = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]);
            if p[0] < crossing {
                inside = !inside;
            }
        }
    }
    inside
}
fn point_segment_sq(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> f64 {
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    let denom = dx * dx + dy * dy;
    let t = if denom <= EPS * EPS { 0.0 } else {
        ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom
    }.clamp(0.0, 1.0);
    (p[0] - a[0] - t * dx).powi(2) + (p[1] - a[1] - t * dy).powi(2)
}

/// True polygon collision test (not axis-aligned bounding box nesting).
pub fn overlaps(a: &[[f64; 2]], b: &[[f64; 2]], gap: f64) -> bool {
    let ab = bounds(a);
    let bb = bounds(b);
    if ab[2] + gap < bb[0] || bb[2] + gap < ab[0]
        || ab[3] + gap < bb[1] || bb[3] + gap < ab[1] {
        return false;
    }
    if contains(a, b[0]) || contains(b, a[0]) {
        return true;
    }
    let clearance_sq = (gap + EPS).powi(2);
    for ai in 0..a.len() {
        let a0 = a[ai];
        let a1 = a[(ai + 1) % a.len()];
        for bi in 0..b.len() {
            let b0 = b[bi];
            let b1 = b[(bi + 1) % b.len()];
            if edges_cross(a0, a1, b0, b1)
                || point_segment_sq(a0, b0, b1) <= clearance_sq
                || point_segment_sq(a1, b0, b1) <= clearance_sq
                || point_segment_sq(b0, a0, a1) <= clearance_sq
                || point_segment_sq(b1, a0, a1) <= clearance_sq {
                return true;
            }
        }
    }
    false
}
#[cfg(test)]
fn moved(local: &[[f64; 2]], x: f64, y: f64) -> Vec<[f64; 2]> {
    local.iter().map(|p| [p[0] + x, p[1] + y]).collect()
}
pub fn valid_placement(part: &Part, placed: &[Part], sheet: &Sheet, gap: f64, margin: f64) -> bool {
    let vertices = part.world_points();
    let b = bounds(&vertices);
    if b[0] < margin - EPS || b[1] < margin - EPS
        || b[2] > sheet.width_mm - margin + EPS
        || b[3] > sheet.height_mm - margin + EPS {
        return false;
    }
    !placed.iter().any(|other| overlaps(&vertices, &other.world_points(), gap))
}

/// Nest all parts on a regular mm search grid, considering quarter-turn rotations.
/// If any part cannot fit, return an error without mutating the source sheet.
pub fn nest(sheet: &Sheet, gap: f64, margin: f64, step_mm: f64) -> Result<Sheet, String> {
    sheet.validate()?;
    if !gap.is_finite() || !margin.is_finite() || !step_mm.is_finite()
        || gap < 0.0 || margin < 0.0 || !(0.5..=50.0).contains(&step_mm) {
        return Err("Gap and margin must be nonnegative; step must be 0.5–50 mm".into());
    }
    let mut parts = sheet.parts.clone();
    parts.sort_by(|a, b| area(&b.outline).total_cmp(&area(&a.outline))
        .then_with(|| a.id.cmp(&b.id)));
    let mut placed = Vec::<Part>::with_capacity(parts.len());
    for mut part in parts {
        let mut found: Option<(f64, f64, u8)> = None;
        for turn in 0..4 {
            part.quarter_turns = turn;
            let size = part.size();
            let usable_x = sheet.width_mm - margin - size[0];
            let usable_y = sheet.height_mm - margin - size[1];
            if usable_x < margin - EPS || usable_y < margin - EPS {
                continue;
            }
            let count_x = ((usable_x - margin) / step_mm).floor() as usize;
            let count_y = ((usable_y - margin) / step_mm).floor() as usize;
            // Bound synchronous search so an accidentally tiny grid cannot freeze
            // the editor for enormous CNC sheets.
            if (count_x + 2).saturating_mul(count_y + 2) > 150_000 {
                return Err("Nesting search is too dense for the sheet. Increase search step.".into());
            }
            // Always evaluate the last legal boundary, not only grid points.
            for row in 0..=count_y + 1 {
                let y = if row == count_y + 1 { usable_y } else { margin + row as f64 * step_mm };
                for col in 0..=count_x + 1 {
                    let x = if col == count_x + 1 { usable_x } else { margin + col as f64 * step_mm };
                    part.x = x;
                    part.y = y;
                    if valid_placement(&part, &placed, sheet, gap, margin)
                        && found.is_none_or(|previous| (y, x) < (previous.1, previous.0)) {
                        found = Some((x, y, turn));
                    }
                }
                if found.is_some_and(|f| f.1 <= y + EPS) {
                    break;
                }
            }
        }
        let (x, y, turn) = found.ok_or_else(|| {
            format!("Unable to place '{}' within this sheet and clearance.", part.name)
        })?;
        part.x = x;
        part.y = y;
        part.quarter_turns = turn;
        placed.push(part);
    }
    let mut output = sheet.clone();
    placed.sort_by_key(|part| part.id);
    output.parts = placed;
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::{rectangle, star};
    fn part(id: u64, outline: Vec<[f64; 2]>) -> Part {
        Part { id, name: id.to_string(), outline, x: 0.0, y: 0.0, quarter_turns: 0 }
    }
    #[test]
    fn concave_shapes_do_not_false_positive_on_bounding_boxes() {
        let concave = vec![[0.0,0.0], [12.0,0.0], [12.0,3.0], [3.0,3.0], [3.0,12.0], [0.0,12.0]];
        let cavity = vec![[5.0,5.0], [9.0,5.0], [9.0,9.0], [5.0,9.0]];
        assert!(!overlaps(&concave, &cavity, 0.0));
        assert!(overlaps(&concave, &cavity, 2.1));
    }
    #[test]
    fn rectangles_touching_fail_required_clearance() {
        let a = rectangle(8.0, 10.0);
        let b = moved(&rectangle(8.0, 10.0), 8.0, 0.0);
        assert!(overlaps(&a, &b, 0.0));
        assert!(overlaps(&a, &b, 1.0));
        assert!(!overlaps(&a, &moved(&b, 2.0, 0.0), 1.0));
    }
    #[test]
    fn nesting_is_deterministic_and_enforces_stock_margin() {
        let mut sheet = Sheet { width_mm: 45.0, height_mm: 40.0, ..Sheet::default() };
        sheet.parts = vec![part(1, rectangle(10.0, 10.0)), part(2, star(5, 8.0, 3.0)), part(3, rectangle(18.0, 7.0))];
        let result = nest(&sheet, 2.0, 3.0, 2.0).unwrap();
        assert_eq!(result, nest(&sheet, 2.0, 3.0, 2.0).unwrap());
        for (index, p) in result.parts.iter().enumerate() {
            assert!(valid_placement(p, &result.parts[..index], &result, 2.0, 3.0));
        }
        assert_eq!(sheet.parts[0].x, 0.0);
    }
    #[test]
    fn dense_search_is_rejected_before_ui_work_can_stall() {
        let mut sheet = Sheet { width_mm: 10_000.0, height_mm: 10_000.0, ..Sheet::default() };
        sheet.parts.push(part(1, rectangle(10.0, 10.0)));
        assert!(nest(&sheet, 1.0, 1.0, 0.5).unwrap_err().contains("too dense"));
    }
    #[test]
    fn impossible_nest_fails_without_mutating_sheet() {
        let mut sheet = Sheet { width_mm: 10.0, height_mm: 10.0, ..Sheet::default() };
        sheet.parts = vec![part(1, rectangle(20.0, 20.0))];
        let previous = sheet.clone();
        assert!(nest(&sheet, 1.0, 1.0, 1.0).is_err());
        assert_eq!(sheet, previous);
    }
}
