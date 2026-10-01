//! Isolated browser CAM prototype. Does NOT produce machine-ready NC programs.
//! The native Python/PyO3/Rayon desktop crate is intentionally left untouched.
use serde::{Deserialize, Serialize};

const MAX_MOVES: usize = 250_000;
const EPS: f64 = 1e-8;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PocketRequest {
    pub stock_width_mm: f64,
    pub stock_height_mm: f64,
    pub stock_thickness_mm: f64,
    pub x_mm: f64,
    pub y_mm: f64,
    pub width_mm: f64,
    pub height_mm: f64,
    pub cutter_diameter_mm: f64,
    pub target_depth_mm: f64,
    pub stepover_mm: f64,
    pub stepdown_mm: f64,
    pub safe_z_mm: f64,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Motion {
    pub x_mm: f64,
    pub y_mm: f64,
    pub z_mm: f64,
    pub kind: &'static str,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PocketPreview {
    pub moves: Vec<Motion>,
    pub passes: usize,
    pub rows_per_pass: usize,
    pub warning: &'static str,
}

fn finite_positive(value: f64) -> bool { value.is_finite() && value > 0.0 }

fn validate(req: &PocketRequest) -> Result<(), String> {
    for (label, value) in [
        ("stock width", req.stock_width_mm),
        ("stock height", req.stock_height_mm),
        ("stock thickness", req.stock_thickness_mm),
        ("pocket width", req.width_mm),
        ("pocket height", req.height_mm),
        ("cutter diameter", req.cutter_diameter_mm),
        ("cut depth", req.target_depth_mm),
        ("stepover", req.stepover_mm),
        ("stepdown", req.stepdown_mm),
        ("safe Z", req.safe_z_mm),
    ] {
        if !finite_positive(value) { return Err(format!("{label} must be finite and greater than zero")); }
    }
    if !req.x_mm.is_finite() || !req.y_mm.is_finite() || req.x_mm < 0.0 || req.y_mm < 0.0 {
        return Err("Pocket X/Y must be finite, nonnegative stock coordinates".into());
    }
    if req.x_mm + req.width_mm > req.stock_width_mm + EPS
        || req.y_mm + req.height_mm > req.stock_height_mm + EPS {
        return Err("Pocket extends outside stock bounds".into());
    }
    if req.target_depth_mm > req.stock_thickness_mm + EPS {
        return Err("Cut depth exceeds stock thickness".into());
    }
    if req.cutter_diameter_mm > req.width_mm + EPS
        || req.cutter_diameter_mm > req.height_mm + EPS {
        return Err("Cutter cannot fit inside the pocket".into());
    }
    if req.stepover_mm > req.cutter_diameter_mm + EPS {
        return Err("Stepover must not exceed the cutter diameter".into());
    }
    Ok(())
}

pub fn plan_pocket(req: &PocketRequest) -> Result<PocketPreview, String> {
    validate(req)?;
    let radius = req.cutter_diameter_mm / 2.0;
    let xmin = req.x_mm + radius;
    let xmax = req.x_mm + req.width_mm - radius;
    let ymin = req.y_mm + radius;
    let ymax = req.y_mm + req.height_mm - radius;
    let rows = ((ymax - ymin) / req.stepover_mm).ceil() as usize + 1;
    let passes = (req.target_depth_mm / req.stepdown_mm).ceil() as usize;
    let total = rows.checked_mul(passes)
        .and_then(|count| count.checked_mul(4))
        .ok_or("Preview move count exceeds the supported limit")?;
    if total > MAX_MOVES {
        return Err("Preview is too large. Increase stepover/stepdown or reduce the pocket size.".into());
    }
    let mut moves = Vec::with_capacity(total);
    for pass in 1..=passes {
        let z = -(req.target_depth_mm).min(pass as f64 * req.stepdown_mm);
        for row in 0..rows {
            let y = (ymin + row as f64 * req.stepover_mm).min(ymax);
            let (from_x, to_x) = if row % 2 == 0 { (xmin, xmax) } else { (xmax, xmin) };
            moves.push(Motion { x_mm: from_x, y_mm: y, z_mm: req.safe_z_mm, kind: "rapid" });
            moves.push(Motion { x_mm: from_x, y_mm: y, z_mm: z, kind: "plunge" });
            moves.push(Motion { x_mm: to_x, y_mm: y, z_mm: z, kind: "cut" });
            moves.push(Motion { x_mm: to_x, y_mm: y, z_mm: req.safe_z_mm, kind: "retract" });
        }
    }
    Ok(PocketPreview {
        moves, passes, rows_per_pass: rows,
        warning: "Visualization only. No fixture, holder, machine-limit, entry, or post-export G-code verification. Not approved for machining.",
    })
}

#[cfg(target_arch = "wasm32")]
mod web {
    use super::{plan_pocket, PocketRequest};
    use wasm_bindgen::prelude::*;

    #[wasm_bindgen]
    pub fn preview_pocket(request: JsValue) -> Result<JsValue, JsValue> {
        let parsed: PocketRequest = serde_wasm_bindgen::from_value(request)
            .map_err(|error| JsValue::from_str(&format!("Invalid settings: {error}")))?;
        let planned = plan_pocket(&parsed).map_err(|error| JsValue::from_str(&error))?;
        serde_wasm_bindgen::to_value(&planned)
            .map_err(|error| JsValue::from_str(&error.to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> PocketRequest {
        PocketRequest {
            stock_width_mm: 200.0, stock_height_mm: 120.0, stock_thickness_mm: 18.0,
            x_mm: 40.0, y_mm: 30.0, width_mm: 80.0, height_mm: 50.0,
            cutter_diameter_mm: 6.0, target_depth_mm: 3.0, stepover_mm: 3.0,
            stepdown_mm: 1.5, safe_z_mm: 5.0,
        }
    }

    #[test]
    fn plans_correct_passes_and_safe_retractions() {
        let p = plan_pocket(&base()).unwrap();
        assert_eq!(p.passes, 2);
        assert_eq!(p.moves.len(), p.passes * p.rows_per_pass * 4);
        assert!(p.moves.iter().filter(|m| m.kind == "rapid" || m.kind == "retract")
            .all(|m| (m.z_mm - 5.0).abs() < 1e-9));
        assert!(p.moves.iter().filter(|m| m.kind == "cut")
            .all(|m| m.x_mm >= 43.0 && m.x_mm <= 117.0
                && m.y_mm >= 33.0 && m.y_mm <= 77.0));
        assert_eq!(p.moves.last().unwrap().kind, "retract");
        assert_eq!(p.moves[p.moves.len() - 2].z_mm, -3.0);
    }

    #[test]
    fn fails_closed_on_unsafe_or_nonfinite_input() {
        let mut p = base(); p.target_depth_mm = 19.0;
        assert!(plan_pocket(&p).unwrap_err().contains("thickness"));
        p = base(); p.x_mm = -0.1;
        assert!(plan_pocket(&p).unwrap_err().contains("nonnegative"));
        p = base(); p.stepover_mm = 7.0;
        assert!(plan_pocket(&p).unwrap_err().contains("Stepover"));
        p = base(); p.safe_z_mm = f64::NAN;
        assert!(plan_pocket(&p).is_err());
    }

    #[test]
    fn supports_serde_round_trip() {
        let json = serde_json::to_string(&base()).unwrap();
        assert!(json.contains("stockWidthMm"));
        let req: PocketRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(plan_pocket(&req).unwrap().passes, 2);
    }

    #[test]
    fn rejects_path_explosion_before_allocation() {
        let mut p = base();
        p.stepover_mm = 1e-10;
        assert!(plan_pocket(&p).is_err());
    }
}
