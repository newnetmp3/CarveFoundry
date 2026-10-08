//! Editable 2D source geometry independent of the safety-critical CAM engine.
use serde::{Deserialize, Serialize};
use std::f64::consts::PI;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Part {
    pub id: u64,
    pub name: String,
    pub outline: Vec<[f64; 2]>,
    pub x: f64,
    pub y: f64,
    #[serde(default)]
    pub quarter_turns: u8,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Sheet {
    pub format_version: u32,
    pub name: String,
    pub width_mm: f64,
    pub height_mm: f64,
    pub parts: Vec<Part>,
}

impl Default for Sheet {
    fn default() -> Self {
        Self {
            format_version: 1,
            name: "Untitled sheet".into(),
            width_mm: 300.0,
            height_mm: 200.0,
            parts: vec![],
        }
    }
}

pub fn polygon(sides: usize, radius: f64) -> Vec<[f64; 2]> {
    (0..sides).map(|i| {
        let angle = 2.0 * PI * i as f64 / sides as f64 - PI / 2.0;
        [radius * angle.cos(), radius * angle.sin()]
    }).collect()
}

pub fn star(points: usize, outer: f64, inner: f64) -> Vec<[f64; 2]> {
    (0..points * 2).map(|i| {
        let angle = PI * i as f64 / points as f64 - PI / 2.0;
        let radius = if i % 2 == 0 { outer } else { inner };
        [radius * angle.cos(), radius * angle.sin()]
    }).collect()
}

pub fn rectangle(width: f64, height: f64) -> Vec<[f64; 2]> {
    vec![[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]]
}

pub fn ellipse(width: f64, height: f64, segments: usize) -> Vec<[f64; 2]> {
    (0..segments).map(|i| {
        let angle = 2.0 * PI * i as f64 / segments as f64;
        [width * (1.0 + angle.cos()) * 0.5, height * (1.0 + angle.sin()) * 0.5]
    }).collect()
}

pub fn bounds(points: &[[f64; 2]]) -> [f64; 4] {
    let mut b = [f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY];
    for p in points {
        b[0] = b[0].min(p[0]);
        b[1] = b[1].min(p[1]);
        b[2] = b[2].max(p[0]);
        b[3] = b[3].max(p[1]);
    }
    b
}

pub fn area(points: &[[f64; 2]]) -> f64 {
    let mut sum = 0.0;
    for i in 0..points.len() {
        let p = points[i];
        let q = points[(i + 1) % points.len()];
        sum += p[0] * q[1] - q[0] * p[1];
    }
    0.5 * sum.abs()
}

pub fn oriented(outline: &[[f64; 2]], quarter_turns: u8) -> Vec<[f64; 2]> {
    let mut rotated: Vec<[f64; 2]> = outline.iter().map(|p| match quarter_turns % 4 {
        0 => *p,
        1 => [-p[1], p[0]],
        2 => [-p[0], -p[1]],
        _ => [p[1], -p[0]],
    }).collect();
    let b = bounds(&rotated);
    for p in &mut rotated {
        p[0] -= b[0];
        p[1] -= b[1];
    }
    rotated
}

impl Part {
    pub fn local_points(&self) -> Vec<[f64; 2]> {
        oriented(&self.outline, self.quarter_turns)
    }
    pub fn world_points(&self) -> Vec<[f64; 2]> {
        self.local_points().into_iter().map(|p| [p[0] + self.x, p[1] + self.y]).collect()
    }
    pub fn size(&self) -> [f64; 2] {
        let b = bounds(&self.local_points());
        [b[2] - b[0], b[3] - b[1]]
    }
}

impl Sheet {
    pub fn next_id(&self) -> u64 {
        self.parts.iter().map(|p| p.id).max().unwrap_or(0) + 1
    }
    pub fn validate(&self) -> Result<(), String> {
        if self.format_version != 1 {
            return Err("Unsupported sheet format version".into());
        }
        if !self.width_mm.is_finite() || !self.height_mm.is_finite()
            || self.width_mm <= 0.0 || self.height_mm <= 0.0
            || self.width_mm > 100_000.0 || self.height_mm > 100_000.0 {
            return Err("Sheet size must be finite, positive and within 100 m".into());
        }
        let mut ids = std::collections::HashSet::new();
        if self.parts.len() > 512 {
            return Err("Too many parts for this layout workspace (512 maximum)".into());
        }
        for part in &self.parts {
            if !ids.insert(part.id) || part.name.len() > 256 || part.outline.len() < 3
                || part.outline.len() > 1024 || part.quarter_turns > 3
                || !part.x.is_finite() || !part.y.is_finite()
                || part.outline.iter().any(|p| !p[0].is_finite() || !p[1].is_finite())
                || area(&part.outline) < 1e-8 {
                return Err(format!("Invalid part geometry or identifier: {}", part.name));
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn shapes_and_rotation_are_finite_and_deterministic() {
        assert_eq!(rectangle(10.0, 5.0).len(), 4);
        assert_eq!(polygon(7, 10.0).len(), 7);
        assert_eq!(star(5, 15.0, 6.0).len(), 10);
        assert_eq!(ellipse(10.0, 5.0, 48).len(), 48);
        let p = Part { id: 1, name: "R".into(), outline: rectangle(10.0, 4.0), x: 2.0, y: 3.0, quarter_turns: 1 };
        assert_eq!(p.size(), [4.0, 10.0]);
        assert_eq!(bounds(&p.world_points()), [2.0, 3.0, 6.0, 13.0]);
    }
    #[test]
    fn serialized_document_has_explicit_version() {
        let sheet = Sheet::default();
        let json = serde_json::to_string(&sheet).unwrap();
        assert_eq!(serde_json::from_str::<Sheet>(&json).unwrap(), sheet);
        assert!(json.contains("format_version"));
    }
    #[test]
    fn invalid_geometry_and_duplicate_identifiers_are_rejected() {
        let mut sheet = Sheet::default();
        sheet.parts.push(Part { id: 1, name: "A".into(), outline: rectangle(5.0, 5.0), x: 0.0, y: 0.0, quarter_turns: 0 });
        sheet.parts.push(sheet.parts[0].clone());
        assert!(sheet.validate().is_err());
    }
}
