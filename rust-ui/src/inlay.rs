//! Geometry-only paired pocket/plug outlines for the native Rust layout Studio.
//!
//! Only strictly convex, single-ring polygons are supported here. Cutter taper
//! is a conservative design setback, NOT a verified fit or a cutter path.
//! SVG outputs must go through authoritative CAM and fixture-aware preflight.
use crate::geometry::{Part, Sheet, bounds};
use crate::source_placement::SourcePlacement;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::Read;
use std::path::Path;

const EPS: f64 = 1e-8;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct InlaySettings {
    pub cutter_diameter_mm: f64,
    pub included_angle_deg: f64,
    pub tip_diameter_mm: f64,
    pub pocket_depth_mm: f64,
    pub plug_depth_mm: f64,
    pub engagement_mm: f64,
    pub glue_gap_mm: f64,
    pub fit_clearance_mm: f64,
    pub pocket_stock_thickness_mm: f64,
    pub plug_stock_thickness_mm: f64,
}
impl Default for InlaySettings {
    fn default() -> Self {
        Self {
            cutter_diameter_mm: 6.35,
            included_angle_deg: 60.0,
            tip_diameter_mm: 0.0,
            pocket_depth_mm: 2.0,
            plug_depth_mm: 2.5,
            engagement_mm: 1.5,
            glue_gap_mm: 0.3,
            fit_clearance_mm: 0.15,
            pocket_stock_thickness_mm: 19.0,
            plug_stock_thickness_mm: 19.0,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct InlayPlan {
    pub format_version: u32,
    pub part_id: u64,
    pub part_name: String,
    pub stock_width_mm: f64,
    pub stock_height_mm: f64,
    pub settings: InlaySettings,
    pub taper_allowance_mm: f64,
    pub total_plug_setback_mm: f64,
    pub pocket_xy: Vec<[f64; 2]>,
    pub plug_xy: Vec<[f64; 2]>,
    pub pocket_area_mm2: f64,
    pub plug_area_mm2: f64,
    pub produces_gcode: bool,
    pub requires_cam_and_preflight: bool,
}

fn cross(a: [f64; 2], b: [f64; 2]) -> f64 {
    a[0] * b[1] - a[1] * b[0]
}
fn subtract(a: [f64; 2], b: [f64; 2]) -> [f64; 2] {
    [a[0] - b[0], a[1] - b[1]]
}
fn signed_area(points: &[[f64; 2]]) -> f64 {
    (0..points.len()).map(|i| cross(points[i], points[(i + 1) % points.len()])).sum::<f64>() / 2.0
}
fn finite_positive(name: &str, v: f64) -> Result<(), String> {
    if !v.is_finite() || v <= 0.0 || v > 100_000.0 {
        return Err(format!("{name} must be finite, positive, and at most 100,000 mm"));
    }
    Ok(())
}
fn checked_outline(points: &[[f64; 2]]) -> Result<f64, String> {
    if !(3..=1024).contains(&points.len())
        || points.iter().any(|p| !p[0].is_finite() || !p[1].is_finite()) {
        return Err("Inlay needs a bounded, finite closed polygon".into());
    }
    let a = signed_area(points);
    if a.abs() < EPS { return Err("Inlay polygon has no usable area".into()); }
    let sign = a.signum();
    for i in 0..points.len() {
        let prev = points[(i + points.len() - 1) % points.len()];
        let cur = points[i];
        let next = points[(i + 1) % points.len()];
        let u = subtract(cur, prev);
        let v = subtract(next, cur);
        let turn = cross(u, v) * sign;
        // Reject concave shapes, degenerate corners and nearly parallel
        // offset lines; no silent polygon clipping or changed topology.
        if turn <= EPS || u[0].hypot(u[1]) <= EPS || v[0].hypot(v[1]) <= EPS {
            return Err("Inlay currently requires a strictly convex polygon without collinear/repeated vertices".into());
        }
    }
    Ok(a)
}

/// Intersect adjacent inward-shifted edge lines. Exact for straight convex
/// outlines; inward displacement measured normal to the original edges.
fn inward_offset(points: &[[f64; 2]], distance: f64) -> Result<Vec<[f64; 2]>, String> {
    let winding = checked_outline(points)?.signum();
    if !distance.is_finite() || distance <= 0.0 {
        return Err("Plug setback must be finite and positive".into());
    }
    let mut shifted = Vec::with_capacity(points.len());
    for i in 0..points.len() {
        let prev = points[(i + points.len() - 1) % points.len()];
        let cur = points[i];
        let next = points[(i + 1) % points.len()];
        let u = subtract(cur, prev);
        let v = subtract(next, cur);
        let lu = u[0].hypot(u[1]);
        let lv = v[0].hypot(v[1]);
        let inside_u = [-u[1] * winding / lu, u[0] * winding / lu];
        let inside_v = [-v[1] * winding / lv, v[0] * winding / lv];
        let pu = [cur[0] + distance * inside_u[0], cur[1] + distance * inside_u[1]];
        let pv = [cur[0] + distance * inside_v[0], cur[1] + distance * inside_v[1]];
        let det = cross(u, v);
        if det.abs() <= EPS {
            return Err("Cannot offset nearly parallel polygon edges".into());
        }
        let delta = subtract(pv, pu);
        let t = cross(delta, v) / det;
        let p = [pu[0] + t * u[0], pu[1] + t * u[1]];
        if p.iter().any(|x| !x.is_finite() || x.abs() > 100_000.0) {
            return Err("Inset would overflow design coordinate bounds".into());
        }
        shifted.push(p);
    }
    let area = checked_outline(&shifted)?;
    if area.signum() != winding || area.abs() >= signed_area(points).abs() {
        return Err("Plug setback collapses or inverts the input contour".into());
    }
    // A valid inset vertex must lie strictly within every original convex
    // edge's interior half-plane; otherwise it crossed the medial axis.
    for p in &shifted {
        for i in 0..points.len() {
            let e = subtract(points[(i + 1) % points.len()], points[i]);
            let signed_distance = cross(e, subtract(*p, points[i])) * winding
                / e[0].hypot(e[1]);
            if signed_distance < distance - EPS {
                return Err("Plug setback is larger than the available contour width".into());
            }
        }
    }
    Ok(shifted)
}

pub fn plan(sheet: &Sheet, part: &Part, settings: &InlaySettings) -> Result<InlayPlan, String> {
    sheet.validate()?;
    if !sheet.parts.iter().any(|p| p == part) {
        return Err("Selected inlay source is no longer in the active sheet".into());
    }
    for (name, value) in [
        ("Cutter diameter", settings.cutter_diameter_mm),
        ("Pocket depth", settings.pocket_depth_mm),
        ("Plug depth", settings.plug_depth_mm),
        ("Engagement depth", settings.engagement_mm),
        ("Pocket material thickness", settings.pocket_stock_thickness_mm),
        ("Plug material thickness", settings.plug_stock_thickness_mm),
    ] {
        finite_positive(name, value)?;
    }
    if !settings.included_angle_deg.is_finite()
        || !(10.0..=120.0).contains(&settings.included_angle_deg) {
        return Err("Cutter included angle must be between 10° and 120°".into());
    }
    for (name, v) in [("Tip diameter", settings.tip_diameter_mm),
                      ("Fit clearance", settings.fit_clearance_mm),
                      ("Glue gap", settings.glue_gap_mm)] {
        if !v.is_finite() || !(0.0..=100.0).contains(&v) {
            return Err(format!("{name} must be finite and within 0–100 mm"));
        }
    }
    if settings.fit_clearance_mm <= 0.0 {
        return Err("Fit clearance must be greater than zero".into());
    }
    if settings.tip_diameter_mm >= settings.cutter_diameter_mm {
        return Err("Tip diameter must be smaller than cutter diameter".into());
    }
    if settings.engagement_mm > settings.pocket_depth_mm
        || settings.engagement_mm > settings.plug_depth_mm {
        return Err("Engagement cannot exceed either recess depth".into());
    }
    if settings.pocket_depth_mm >= settings.pocket_stock_thickness_mm
        || settings.plug_depth_mm + settings.glue_gap_mm >= settings.plug_stock_thickness_mm {
        return Err("Depth plus glue allowance must remain inside the material thickness".into());
    }
    let slope = (settings.included_angle_deg.to_radians() / 2.0).tan();
    let max_depth = settings.pocket_depth_mm.max(settings.plug_depth_mm);
    let tool_radius_at_depth = settings.tip_diameter_mm / 2.0 + max_depth * slope;
    if tool_radius_at_depth > settings.cutter_diameter_mm / 2.0 + EPS {
        return Err("Requested depth exceeds the cutter's usable conical profile".into());
    }
    let pocket = part.world_points();
    checked_outline(&pocket)?;
    let b = bounds(&pocket);
    if b[0] < 0.0 || b[1] < 0.0
        || b[2] > sheet.width_mm || b[3] > sheet.height_mm {
        return Err("Inlay source contour must fit entirely within the stock".into());
    }
    let taper = settings.engagement_mm * slope;
    let setback = settings.fit_clearance_mm + taper;
    let plug = inward_offset(&pocket, setback)?;
    Ok(InlayPlan {
        format_version: 1, part_id: part.id, part_name: part.name.clone(),
        stock_width_mm: sheet.width_mm, stock_height_mm: sheet.height_mm,
        settings: settings.clone(), taper_allowance_mm: taper,
        total_plug_setback_mm: setback,
        pocket_area_mm2: signed_area(&pocket).abs(),
        plug_area_mm2: signed_area(&plug).abs(),
        pocket_xy: pocket, plug_xy: plug,
        produces_gcode: false, requires_cam_and_preflight: true,
    })
}

fn document(plan: &InlayPlan, points: &[[f64; 2]], id: &str) -> String {
    let coords = points.iter().map(|p| format!("{:.6},{:.6}", p[0], p[1]))
        .collect::<Vec<_>>().join(" ");
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{:.4}mm\" height=\"{:.4}mm\" viewBox=\"0 0 {:.4} {:.4}\">\n  <g transform=\"translate(0,{:.4}) scale(1,-1)\" fill=\"none\" stroke=\"#123958\" stroke-width=\"0.15\">\n    <polygon id=\"{}\" points=\"{}\" />\n  </g>\n</svg>\n",
        plan.stock_width_mm, plan.stock_height_mm,
        plan.stock_width_mm, plan.stock_height_mm, plan.stock_height_mm, id, coords,
    )
}
fn sha256_file(path: &Path) -> Result<String, String> {
    let mut stream = File::open(path).map_err(|e| format!("Cannot inspect CF3D source: {e}"))?;
    let mut hash = Sha256::new();
    let mut bytes = [0u8; 65_536];
    loop {
        let n = stream.read(&mut bytes).map_err(|e| e.to_string())?;
        if n == 0 { break; }
        hash.update(&bytes[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

/// Save three DESIGN artifacts into a previously nonexistent directory.
/// Existing files and CF3D projects are never overwritten or mutated.
pub fn export_pair(
    directory: &Path, plan: &InlayPlan, source: Option<&SourcePlacement>,
) -> Result<(), String> {
    let source_metadata = if let Some(link) = source {
        let uuid = link.uuid_by_part_id.get(&plan.part_id)
            .ok_or("Inlay selection is not linked to an original CF3D source UUID")?;
        let baseline = link.baseline.parts.iter().find(|p| p.id == plan.part_id)
            .ok_or("Original CF3D part no longer matches the inlay source")?;
        if baseline.name != plan.part_name {
            return Err("Inlay part was renamed since CF3D inspection".into());
        }
        let original = baseline.world_points();
        if original.len() != plan.pocket_xy.len() {
            return Err("Inlay source polygon topology differs from the linked CF3D".into());
        }
        let delta = subtract(plan.pocket_xy[0], original[0]);
        if original.iter().zip(&plan.pocket_xy).any(|(a, b)| {
            (a[0] + delta[0] - b[0]).abs() > 1e-7
                || (a[1] + delta[1] - b[1]).abs() > 1e-7
        }) {
            return Err("Inlay geometry differs from the source CF3D; placement-only edits permitted".into());
        }
        if sha256_file(Path::new(&link.source_path))? != link.source_sha256 {
            return Err("Source CF3D changed; re-import before exporting inlay design".into());
        }
        serde_json::json!({
            "cf3d_path": link.source_path,
            "cf3d_sha256": link.source_sha256,
            "source_item_uuid": uuid,
        })
    } else {
        serde_json::json!({"source": "native-rust-layout", "cf3d_sha256": null})
    };
    let manifest = serde_json::json!({
        "design_only": true,
        "fit_and_machine_clearance_unverified": true,
        "physical_mirroring_not_applied": true,
        "requires_separate_cam_generation_and_fixture_aware_preflight": true,
        "source": source_metadata,
        "plan": plan,
    });
    let json = serde_json::to_vec_pretty(&manifest).map_err(|e| e.to_string())?;
    // Exclusive directory creation avoids overwrite of any prior machining job.
    fs::create_dir(directory).map_err(|e| format!("Use a NEW output directory: {e}"))?;
    let outcome = (|| -> Result<(), String> {
        fs::write(directory.join("pocket-outline.svg"), document(plan, &plan.pocket_xy, "pocket-outline"))
            .map_err(|e| e.to_string())?;
        fs::write(directory.join("plug-outline.svg"), document(plan, &plan.plug_xy, "plug-outline"))
            .map_err(|e| e.to_string())?;
        fs::write(directory.join("inlay-design.json"), json).map_err(|e| e.to_string())?;
        if let Some(link) = source {
            if sha256_file(Path::new(&link.source_path))? != link.source_sha256 {
                return Err("Source CF3D changed while exporting; design output discarded".into());
            }
        }
        Ok(())
    })();
    if outcome.is_err() {
        let _ = fs::remove_dir_all(directory);
    }
    outcome
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::rectangle;

    fn sheet_and_part(outline: Vec<[f64; 2]>) -> (Sheet, Part) {
        let part = Part {
            id: 7, name: "Pocket".into(), outline,
            x: 20.0, y: 20.0, quarter_turns: 0,
        };
        let sheet = Sheet { parts: vec![part.clone()], ..Sheet::default() };
        (sheet, part)
    }
    #[test]
    fn rectangle_pair_has_expected_clearance_taper_and_area() {
        let (s, p) = sheet_and_part(rectangle(50.0, 30.0));
        let settings = InlaySettings::default();
        let result = plan(&s, &p, &settings).unwrap();
        let d = settings.fit_clearance_mm + settings.engagement_mm
            * (settings.included_angle_deg.to_radians() / 2.0).tan();
        assert!((result.plug_xy[0][0] - (20.0 + d)).abs() < 1e-7);
        assert!((result.plug_xy[0][1] - (20.0 + d)).abs() < 1e-7);
        assert!(result.plug_area_mm2 < result.pocket_area_mm2);
        assert!(!result.produces_gcode);
        assert!(result.requires_cam_and_preflight);
    }
    #[test]
    fn opposite_winding_yields_same_inset_envelope() {
        let (s, p) = sheet_and_part(rectangle(35.0, 20.0));
        let a = plan(&s, &p, &InlaySettings::default()).unwrap();
        let (s, p) = sheet_and_part(p.outline.into_iter().rev().collect());
        let b = plan(&s, &p, &InlaySettings::default()).unwrap();
        for i in 0..4 {
            assert!((a.plug_area_mm2 - b.plug_area_mm2).abs() < 1e-7);
            assert!(a.plug_xy[i][0].is_finite() && b.plug_xy[i][1].is_finite());
        }
    }
    #[test]
    fn rejects_concavity_collapses_and_malformed_parameters() {
        let (s, p) = sheet_and_part(vec![
            [0.0, 0.0], [50.0, 0.0], [12.0, 5.0], [50.0, 40.0], [0.0, 40.0],
        ]);
        assert!(plan(&s, &p, &InlaySettings::default()).is_err());
        let (s, p) = sheet_and_part(rectangle(2.0, 2.0));
        assert!(plan(&s, &p, &InlaySettings::default()).is_err());
        let (s, p) = sheet_and_part(rectangle(50.0, 30.0));
        let mut config = InlaySettings::default();
        config.fit_clearance_mm = f64::NAN;
        assert!(plan(&s, &p, &config).is_err());
        config = InlaySettings::default();
        config.plug_depth_mm = 30.0;
        assert!(plan(&s, &p, &config).is_err());
        config = InlaySettings::default();
        config.engagement_mm = 4.0;
        assert!(plan(&s, &p, &config).is_err());
        config = InlaySettings::default();
        config.pocket_stock_thickness_mm = 1.0;
        assert!(plan(&s, &p, &config).is_err());
    }
    #[test]
    fn linked_cf3d_export_requires_unchanged_source_digest_and_geometry() {
        let (sheet, part) = sheet_and_part(rectangle(50.0, 30.0));
        let mut job = plan(&sheet, &part, &InlaySettings::default()).unwrap();
        let unique = format!(
            "cf-inlay-guard-{}-{}",
            std::process::id(),
            std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
        );
        let source_path = std::env::temp_dir().join(format!("{unique}.cf3d"));
        fs::write(&source_path, b"source-project-original").unwrap();
        let link = SourcePlacement {
            source_path: source_path.to_string_lossy().into_owned(),
            source_sha256: sha256_file(&source_path).unwrap(),
            baseline: sheet.clone(),
            uuid_by_part_id: std::collections::BTreeMap::from([(part.id, "uuid-seven".into())]),
        };
        let output = std::env::temp_dir().join(format!("{unique}-result"));
        job.pocket_xy[1][0] += 0.5;
        assert!(export_pair(&output, &job, Some(&link)).is_err());
        assert!(!output.exists());
        job = plan(&sheet, &part, &InlaySettings::default()).unwrap();
        export_pair(&output, &job, Some(&link)).unwrap();
        let data = fs::read_to_string(output.join("inlay-design.json")).unwrap();
        assert!(data.contains("uuid-seven"));
        assert!(data.contains(&link.source_sha256));
        fs::write(&source_path, b"source-project-edited").unwrap();
        let stale_output = std::env::temp_dir().join(format!("{unique}-stale"));
        assert!(export_pair(&stale_output, &job, Some(&link)).is_err());
        assert!(!stale_output.exists());
        fs::remove_dir_all(output).unwrap();
        fs::remove_file(source_path).unwrap();
    }
    #[test]
    fn exclusive_svg_pair_export_has_no_nc_and_refuses_overwrite() {
        let (s, p) = sheet_and_part(rectangle(50.0, 30.0));
        let job = plan(&s, &p, &InlaySettings::default()).unwrap();
        let path = std::env::temp_dir().join(format!(
            "cf-inlay-test-{}-{}", std::process::id(),
            std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
        ));
        export_pair(&path, &job, None).unwrap();
        let manifest = fs::read_to_string(path.join("inlay-design.json")).unwrap();
        let pocket = fs::read_to_string(path.join("pocket-outline.svg")).unwrap();
        let plug = fs::read_to_string(path.join("plug-outline.svg")).unwrap();
        assert!(manifest.contains("\"design_only\": true"));
        assert!(manifest.contains("\"produces_gcode\": false"));
        assert!(pocket.contains("scale(1,-1)"));
        assert!(plug.contains("plug-outline"));
        assert!(export_pair(&path, &job, None).is_err());
        fs::remove_dir_all(path).unwrap();
    }
}
