//! Deterministic, bounded live contour snapping for the Rust-only 2D editor.
//!
//! This module aligns *translations* of one layout object to vertices,
//! midpoints and edges on OTHER layout objects. It never edits vector
//! topology, analytic CF3D sources, cutter geometry, or generated machine
//! motion. Targets are snapshotted once at the start of a drag.
use crate::geometry::{Part, Sheet};
const MAX_TARGET_EDGES: usize = 32_768;
const EPS: f64 = 1e-9;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SnapKind {
    Vertex,
    Midpoint,
    Edge,
}
impl SnapKind {
    pub fn label(self) -> &'static str {
        match self {
            Self::Vertex => "VERTEX",
            Self::Midpoint => "MIDPOINT",
            Self::Edge => "EDGE",
        }
    }
    fn priority(self) -> u8 {
        match self { Self::Vertex => 0, Self::Midpoint => 1, Self::Edge => 2 }
    }
}
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SnapMatch {
    pub kind: SnapKind,
    pub source_xy: [f64; 2],
    pub target_xy: [f64; 2],
    pub target_part_id: u64,
    pub separation_mm: f64,
}
#[derive(Clone, Copy, Debug)]
struct TargetEdge {
    part_id: u64,
    start: [f64; 2],
    end: [f64; 2],
}
#[derive(Clone, Debug, Default)]
pub struct SnapIndex {
    edges: Vec<TargetEdge>,
}
fn finite_point(point: [f64; 2]) -> bool {
    point.iter().all(|v| v.is_finite() && v.abs() <= 100_000.0)
}
fn distance_sq(a: [f64; 2], b: [f64; 2]) -> f64 {
    (a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)
}
fn midpoint(a: [f64; 2], b: [f64; 2]) -> [f64; 2] {
    [(a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5]
}
fn closest_on_segment(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> [f64; 2] {
    let delta = [b[0] - a[0], b[1] - a[1]];
    let length_sq = delta[0].mul_add(delta[0], delta[1] * delta[1]);
    if length_sq <= EPS * EPS { return a; }
    let t = ((p[0] - a[0]) * delta[0] + (p[1] - a[1]) * delta[1])
        / length_sq;
    let t = t.clamp(0.0, 1.0);
    [a[0] + t * delta[0], a[1] + t * delta[1]]
}
fn within_limit(p: [f64; 2], radius_mm: f64) -> bool {
    finite_point(p) && radius_mm.is_finite() && radius_mm > 0.0
        && radius_mm <= 50.0
}
fn preferred(candidate: &SnapMatch, prior: &SnapMatch) -> bool {
    let d_new = candidate.separation_mm;
    let d_old = prior.separation_mm;
    // Design-tool priority is vertex > midpoint > edge within the small
    // screen-pixel snap radius. Between equal features, choose the closest
    // and then the stable source part ID regardless of draw order.
    if candidate.kind != prior.kind {
        return candidate.kind.priority() < prior.kind.priority();
    }
    if d_new + EPS < d_old { return true; }
    if d_old + EPS < d_new { return false; }
    (candidate.target_part_id, candidate.target_xy[0].to_bits(),
     candidate.target_xy[1].to_bits())
        < (prior.target_part_id, prior.target_xy[0].to_bits(),
           prior.target_xy[1].to_bits())
}
impl SnapIndex {
    /// Cache only fixed, source-distinct line-segment targets. Strict size
    /// cap prevents the UI from indexing arbitrary million-node imports.
    pub fn from_sheet(sheet: &Sheet, moving_id: u64) -> Result<Self, String> {
        sheet.validate()?;
        if !sheet.parts.iter().any(|p| p.id == moving_id) {
            return Err("Selected snap source is not in this layout".into());
        }
        let count = sheet.parts.iter().filter(|p| p.id != moving_id)
            .map(|p| p.outline.len()).sum::<usize>();
        if count > MAX_TARGET_EDGES {
            return Err("Too many contour edges for live snapping; reduce layout complexity".into());
        }
        let mut edges = Vec::with_capacity(count);
        // Stable tie resolution independent of z-order and serialized item order.
        let mut parts: Vec<&Part> = sheet.parts.iter().filter(|p| p.id != moving_id).collect();
        parts.sort_by_key(|p| p.id);
        for part in parts {
            let polygon = part.world_points();
            for i in 0..polygon.len() {
                let a = polygon[i];
                let b = polygon[(i + 1) % polygon.len()];
                if !finite_point(a) || !finite_point(b) {
                    return Err("Invalid snap target coordinates".into());
                }
                if distance_sq(a, b) <= EPS * EPS { continue; }
                edges.push(TargetEdge { part_id: part.id, start: a, end: b });
            }
        }
        Ok(Self { edges })
    }

    pub fn target_count(&self) -> usize { self.edges.len() }

    /// Find one grab feature on the MOVING object's existing world polygon.
    /// A deep interior click is not a geometry-snap drag; it still allows grid
    /// or unrestricted movement in Studio without a surprising jump.
    pub fn grab_anchor(part: &Part, pointer_world: [f64; 2], radius_mm: f64)
        -> Option<[f64; 2]>
    {
        if !within_limit(pointer_world, radius_mm) { return None; }
        let ring = part.world_points();
        let radius_sq = radius_mm * radius_mm;
        let mut closest: Option<(f64, u8, [f64; 2])> = None;
        for i in 0..ring.len() {
            let a = ring[i];
            let b = ring[(i + 1) % ring.len()];
            for (kind, candidate) in [
                (SnapKind::Vertex, a),
                (SnapKind::Midpoint, midpoint(a, b)),
                (SnapKind::Edge, closest_on_segment(pointer_world, a, b)),
            ] {
                let d = distance_sq(pointer_world, candidate);
                if d > radius_sq { continue; }
                if closest.is_none_or(|(prev, priority, _)| {
                    kind.priority() < priority || (kind.priority() == priority && d + EPS < prev)
                }) {
                    closest = Some((d, kind.priority(), candidate));
                }
            }
        }
        closest.map(|(_, _, p)| p)
    }

    /// Search fixed objects for a valid nearby node, midpoint or projection.
    /// Pointer movement and tolerance are in stock-world mm, not screen px.
    pub fn nearest(&self, moving_anchor_world: [f64; 2], radius_mm: f64)
        -> Option<SnapMatch>
    {
        if !within_limit(moving_anchor_world, radius_mm) { return None; }
        let r2 = radius_mm * radius_mm;
        let mut best: Option<SnapMatch> = None;
        for edge in &self.edges {
            // Fast reject by segment AABB expanded to the visual snap radius.
            if moving_anchor_world[0] < edge.start[0].min(edge.end[0]) - radius_mm
                || moving_anchor_world[0] > edge.start[0].max(edge.end[0]) + radius_mm
                || moving_anchor_world[1] < edge.start[1].min(edge.end[1]) - radius_mm
                || moving_anchor_world[1] > edge.start[1].max(edge.end[1]) + radius_mm {
                continue;
            }
            for (kind, target) in [
                (SnapKind::Vertex, edge.start),
                (SnapKind::Midpoint, midpoint(edge.start, edge.end)),
                (SnapKind::Edge, closest_on_segment(moving_anchor_world, edge.start, edge.end)),
            ] {
                let d2 = distance_sq(moving_anchor_world, target);
                if d2 > r2 { continue; }
                let candidate = SnapMatch {
                    kind, source_xy: moving_anchor_world,
                    target_xy: target, target_part_id: edge.part_id,
                    separation_mm: d2.sqrt(),
                };
                if best.as_ref().is_none_or(|old| preferred(&candidate, old)) {
                    best = Some(candidate);
                }
            }
        }
        best
    }
}

/// Original placement and original grab point stay stable during a drag.
/// Aligning to a target translates the entire moving contour unchanged.
pub fn snapped_drag_position(
    index: &SnapIndex, original_xy: [f64; 2], grab_world: [f64; 2],
    total_delta: [f64; 2], radius_mm: f64,
) -> Option<([f64; 2], SnapMatch)> {
    if !finite_point(original_xy) || !finite_point(grab_world)
        || !finite_point(total_delta) { return None; }
    let moved = [grab_world[0] + total_delta[0], grab_world[1] + total_delta[1]];
    let found = index.nearest(moved, radius_mm)?;
    let placed = [
        original_xy[0] + total_delta[0] + found.target_xy[0] - moved[0],
        original_xy[1] + total_delta[1] + found.target_xy[1] - moved[1],
    ];
    finite_point(placed).then_some((placed, found))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::{rectangle, Sheet};
    fn rect(id: u64, x: f64, y: f64) -> Part {
        Part { id, name: format!("part{id}"), outline: rectangle(10.0, 8.0),
            x, y, quarter_turns: 0 }
    }
    fn sheet() -> Sheet {
        Sheet { parts: vec![rect(1, 5.0, 5.0), rect(2, 30.0, 15.0)],
            ..Sheet::default() }
    }
    #[test]
    fn excludes_self_and_snaps_other_vertex_exactly() {
        let sheet = sheet();
        let idx = SnapIndex::from_sheet(&sheet, 1).unwrap();
        assert_eq!(idx.target_count(), 4);
        assert!(idx.nearest([5.0, 5.0], 2.0).is_none());
        let (new_position, hit) = snapped_drag_position(
            &idx, [5.0, 5.0], [5.0, 5.0], [24.1, 10.2], 2.0,
        ).unwrap();
        assert_eq!(hit.kind, SnapKind::Vertex);
        assert_eq!(hit.target_part_id, 2);
        assert_eq!(hit.target_xy, [30.0, 15.0]);
        assert_eq!(new_position, [30.0, 15.0]);
    }
    #[test]
    fn midpoint_and_edge_projections_are_distinct_and_exact() {
        let idx = SnapIndex::from_sheet(&sheet(), 1).unwrap();
        let mid = idx.nearest([35.05, 15.04], 1.0).unwrap();
        assert_eq!(mid.kind, SnapKind::Midpoint);
        assert_eq!(mid.target_xy, [35.0, 15.0]);
        let edge = idx.nearest([33.0, 15.1], 1.0).unwrap();
        assert_eq!(edge.kind, SnapKind::Edge);
        assert_eq!(edge.target_xy, [33.0, 15.0]);
    }
    #[test]
    fn grab_anchor_prefers_outline_and_does_not_snap_deep_inside() {
        let part = rect(1, 5.0, 5.0);
        assert_eq!(SnapIndex::grab_anchor(&part, [5.1, 5.1], 0.5), Some([5.0, 5.0]));
        assert_eq!(SnapIndex::grab_anchor(&part, [7.1, 5.2], 0.5), Some([7.1, 5.0]));
        assert_eq!(SnapIndex::grab_anchor(&part, [10.0, 9.0], 0.5), None);
    }
    #[test]
    fn rejects_outside_tolerance_missing_id_and_nonfinite_positions() {
        let idx = SnapIndex::from_sheet(&sheet(), 1).unwrap();
        assert!(SnapIndex::from_sheet(&sheet(), 42).is_err());
        assert!(idx.nearest([29.0, 12.0], 0.2).is_none());
        assert!(idx.nearest([f64::NAN, 0.0], 2.0).is_none());
        assert!(idx.nearest([30.0, 15.0], f64::INFINITY).is_none());
        assert!(snapped_drag_position(&idx, [0.0, 0.0], [0.0, 0.0],
            [f64::INFINITY, 0.0], 1.0).is_none());
    }
    #[test]
    fn ordering_of_fixed_parts_does_not_affect_target_choice() {
        let mut s = sheet();
        s.parts.push(rect(3, 30.0, 15.0));
        let before = SnapIndex::from_sheet(&s, 1).unwrap()
            .nearest([30.2, 15.1], 1.0).unwrap();
        s.parts.swap(1, 2);
        let after = SnapIndex::from_sheet(&s, 1).unwrap()
            .nearest([30.2, 15.1], 1.0).unwrap();
        assert_eq!(before.target_part_id, 2);
        assert_eq!(before, after);
    }
    #[test]
    fn large_layout_refused_before_building_unbounded_edge_index() {
        let mut s = Sheet::default();
        s.parts.push(rect(1, 5.0, 5.0));
        for id in 2..=40 {
            s.parts.push(Part {
                id, name: id.to_string(), outline: (0..1024).map(|i| {
                    let angle = std::f64::consts::TAU * i as f64 / 1024.0;
                    [50.0 + angle.cos(), 50.0 + angle.sin()]
                }).collect(),
                x: 0.0, y: 0.0, quarter_turns: 0,
            });
        }
        assert!(SnapIndex::from_sheet(&s, 1).unwrap_err().contains("Too many"));
    }
}
