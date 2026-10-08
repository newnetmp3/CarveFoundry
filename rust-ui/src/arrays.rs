//! Copy arrays for identical vector parts, validated against stock and clearance.
use crate::geometry::Sheet;
use crate::nesting::valid_placement;

/// Replicate a source part in a row/column grid. Source is the top-left slot.
/// The call is atomic: existing geometry is never mutated on error.
pub fn array_selected(
    source: &Sheet, source_id: u64, rows: usize, columns: usize, gap: f64,
) -> Result<Sheet, String> {
    source.validate()?;
    if rows == 0 || columns == 0 || rows.saturating_mul(columns) > 256 {
        return Err("Array must have 1–256 cells and positive rows/columns".into());
    }
    if !gap.is_finite() || gap < 0.0 {
        return Err("Array gap must be finite and non-negative".into());
    }
    let part = source.parts.iter().find(|p| p.id == source_id)
        .ok_or_else(|| "Select a source part for the array".to_owned())?;
    let step = part.size();
    let mut output = source.clone();
    for row in 0..rows {
        for col in 0..columns {
            if row == 0 && col == 0 { continue; }
            let mut new_part = part.clone();
            new_part.id = output.next_id();
            new_part.name = format!("{} copy {}", part.name, output.parts.len() + 1);
            new_part.x = part.x + col as f64 * (step[0] + gap);
            new_part.y = part.y + row as f64 * (step[1] + gap);
            if !valid_placement(&new_part, &output.parts, &output, gap, 0.0) {
                return Err("Array does not fit stock or collides with an existing part".into());
            }
            output.parts.push(new_part);
        }
    }
    output.validate()?;
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::{Part, rectangle};
    #[test]
    fn array_uses_distinct_ids_and_correct_spacing() {
        let mut sheet = Sheet::default();
        sheet.parts.push(Part { id: 5, name: "Panel".into(), outline: rectangle(20.0, 10.0), x: 3.0, y: 5.0, quarter_turns: 0 });
        let result = array_selected(&sheet, 5, 2, 3, 2.0).unwrap();
        assert_eq!(result.parts.len(), 6);
        assert_eq!((result.parts[1].x, result.parts[1].y), (25.0, 5.0));
        assert_eq!((result.parts[3].x, result.parts[3].y), (3.0, 17.0));
        assert_eq!(sheet.parts.len(), 1);
    }
    #[test]
    fn array_rejects_collisions_and_is_atomic() {
        let mut sheet = Sheet { width_mm: 30.0, height_mm: 30.0, ..Sheet::default() };
        sheet.parts.push(Part { id: 1, name: "Panel".into(), outline: rectangle(20.0, 20.0), x: 0.0, y: 0.0, quarter_turns: 0 });
        let original = sheet.clone();
        assert!(array_selected(&sheet, 1, 2, 2, 1.0).is_err());
        assert_eq!(sheet, original);
    }
}
