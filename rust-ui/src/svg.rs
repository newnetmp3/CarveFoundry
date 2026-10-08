//! 2D stock-relative SVG interchange. Does not produce or validate CNC motion.
use crate::geometry::{Sheet, bounds};

fn xml_attr(value: &str) -> String {
    value.replace('&', "&amp;").replace('"', "&quot;")
        .replace('<', "&lt;").replace('>', "&gt;")
}
pub fn export(sheet: &Sheet) -> Result<String, String> {
    sheet.validate()?;
    let mut out = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{:.4}mm\" height=\"{:.4}mm\" viewBox=\"0 0 {:.4} {:.4}\">\n",
        sheet.width_mm, sheet.height_mm, sheet.width_mm, sheet.height_mm,
    );
    // The SVG canvas uses downward-positive Y; machine coordinates use
    // bottom-left XY0 with upward-positive Y. Flip once at the group boundary.
    out.push_str(&format!(
        "  <g transform=\"translate(0,{:.4}) scale(1,-1)\" fill=\"none\" stroke=\"#212d3a\" stroke-width=\"0.15\">\n",
        sheet.height_mm,
    ));
    for part in &sheet.parts {
        let b = bounds(&part.world_points());
        if b[0] < -1e-6 || b[1] < -1e-6
            || b[2] > sheet.width_mm + 1e-6
            || b[3] > sheet.height_mm + 1e-6 {
            return Err(format!("Part '{}' is outside the stock; adjust layout before exporting.", part.name));
        }
        let coords = part.world_points().iter()
            .map(|p| format!("{:.5},{:.5}", p[0], p[1]))
            .collect::<Vec<_>>().join(" ");
        out.push_str(&format!(
            "    <polygon id=\"part-{}\" data-name=\"{}\" points=\"{}\" />\n",
            part.id, xml_attr(&part.name), coords,
        ));
    }
    out.push_str("  </g>\n</svg>\n");
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::{Part, rectangle};
    #[test]
    fn svg_has_stock_dimensions_and_y_flip() {
        let mut sheet = Sheet::default();
        sheet.parts.push(Part {
            id: 1, name: "A & B".into(), outline: rectangle(10.0, 15.0),
            x: 3.0, y: 5.0, quarter_turns: 0,
        });
        let content = export(&sheet).unwrap();
        assert!(content.contains("width=\"300.0000mm\""));
        assert!(content.contains("translate(0,200.0000) scale(1,-1)"));
        assert!(content.contains("data-name=\"A &amp; B\""));
        assert!(content.contains("3.00000,5.00000"));
    }
    #[test]
    fn svg_refuses_parts_outside_stock() {
        let mut sheet = Sheet::default();
        sheet.parts.push(Part {
            id: 2, name: "outside".into(), outline: rectangle(10.0, 15.0),
            x: 299.0, y: 5.0, quarter_turns: 0,
        });
        assert!(export(&sheet).is_err());
    }
}
