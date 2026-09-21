//! Native cutter-sweep kernel for sampled 2.5D stock verification.
//!
//! This implements the same grid-centre and radial-profile semantics as
//! cam/stock_simulation.py. The independent Python reference remains available
//! through CARVEFOUNDRY_CAM_BACKEND=python, with cross-backend regression tests.
use numpy::{PyReadonlyArray1, PyReadwriteArray2, PyUntypedArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[derive(Clone, Copy)]
enum ProfileKind {
    Flat,
    Ball,
    Cone,
    TaperedBall,
    Custom,
}

fn profile_kind(name: &str) -> PyResult<ProfileKind> {
    match name {
        "flat_end_mill" => Ok(ProfileKind::Flat),
        "ball_nose" => Ok(ProfileKind::Ball),
        "v_bit" | "engraving_cone" => Ok(ProfileKind::Cone),
        "tapered_ball_nose" => Ok(ProfileKind::TaperedBall),
        "custom" => Ok(ProfileKind::Custom),
        _ => Err(PyValueError::new_err("unsupported cutter profile")),
    }
}

struct CutterProfile {
    kind: ProfileKind,
    radius: f64,
    angle_deg: f64,
    tip_radius: f64,
    taper_angle_deg: f64,
    ball_radius: f64,
    points: Vec<(f64, f64)>,
}

impl CutterProfile {
    fn height(&self, distance: f64) -> f64 {
        let r = distance.min(self.radius);
        match self.kind {
            ProfileKind::Flat => 0.0,
            ProfileKind::Ball => {
                self.radius - (self.radius * self.radius - r * r).max(0.0).sqrt()
            }
            ProfileKind::Cone => {
                (r - self.tip_radius).max(0.0) / (self.angle_deg.to_radians() / 2.0).tan()
            }
            ProfileKind::TaperedBall => {
                if r <= self.ball_radius {
                    self.ball_radius - (self.ball_radius * self.ball_radius - r * r).max(0.0).sqrt()
                } else {
                    self.ball_radius
                        + (r - self.ball_radius) / self.taper_angle_deg.to_radians().tan()
                }
            }
            ProfileKind::Custom => {
                // Mirror numpy.interp: constant extension beyond the last knot.
                if r >= self.points[self.points.len() - 1].0 {
                    return self.points[self.points.len() - 1].1;
                }
                let right = self.points.partition_point(|point| point.0 <= r);
                if right == 0 {
                    return self.points[0].1;
                }
                let left = right - 1;
                let (r0, z0) = self.points[left];
                let (r1, z1) = self.points[right];
                z0 + (r - r0) * (z1 - z0) / (r1 - r0)
            }
        }
    }
}

fn sweep_impl(
    surface: &mut [f32],
    x_axis: &[f64],
    y_axis: &[f64],
    start: [f64; 3],
    end: [f64; 3],
    samples: usize,
    stock_bottom: f64,
    cutter: &CutterProfile,
) -> usize {
    let radius = cutter.radius;
    let nx = x_axis.len();
    let mut changed = 0;
    for step in 0..=samples {
        let t = step as f64 / samples as f64;
        let cx = start[0] + t * (end[0] - start[0]);
        let cy = start[1] + t * (end[1] - start[1]);
        let z = start[2] + t * (end[2] - start[2]);
        if z > 0.0
            || cx + radius < x_axis[0]
            || cx - radius > x_axis[nx - 1]
            || cy + radius < y_axis[0]
            || cy - radius > y_axis[y_axis.len() - 1]
        {
            continue;
        }
        let ix0 = x_axis.partition_point(|value| *value < cx - radius);
        let ix1 = x_axis.partition_point(|value| *value <= cx + radius);
        let iy0 = y_axis.partition_point(|value| *value < cy - radius);
        let iy1 = y_axis.partition_point(|value| *value <= cy + radius);
        let rr = radius + 1.0e-9;
        for iy in iy0..iy1 {
            let dy = y_axis[iy] - cy;
            for ix in ix0..ix1 {
                let dx = x_axis[ix] - cx;
                let distance = dx.hypot(dy);
                if distance > rr {
                    continue;
                }
                let new_z = (z + cutter.height(distance)).max(stock_bottom);
                let previous = &mut surface[iy * nx + ix];
                if new_z < f64::from(*previous) - 1.0e-9 {
                    *previous = new_z as f32;
                    changed += 1;
                }
            }
        }
    }
    changed
}

/// Sweep a *cutting* segment, with the source grid modified in place.
///
/// Inputs must already be preflighted. No rapid motion should call this API.
/// Keep the Python solver as an independent validation backend.
#[pyfunction]
#[pyo3(signature = (
    surface, x_axis, y_axis, start, end, samples, stock_bottom,
    kind, diameter, angle_deg, tip_diameter, taper_angle_deg,
    ball_radius, profile_points
))]
#[allow(clippy::too_many_arguments)]
pub(crate) fn sweep_stock_segment<'py>(
    mut surface: PyReadwriteArray2<'py, f32>,
    x_axis: PyReadonlyArray1<'py, f64>,
    y_axis: PyReadonlyArray1<'py, f64>,
    start: [f64; 3],
    end: [f64; 3],
    samples: usize,
    stock_bottom: f64,
    kind: &str,
    diameter: f64,
    angle_deg: f64,
    tip_diameter: f64,
    taper_angle_deg: f64,
    ball_radius: f64,
    profile_points: Vec<(f64, f64)>,
) -> PyResult<usize> {
    let x = x_axis
        .as_slice()
        .map_err(|_| PyValueError::new_err("X axis must be contiguous"))?;
    let y = y_axis
        .as_slice()
        .map_err(|_| PyValueError::new_err("Y axis must be contiguous"))?;
    if x.len() < 2 || y.len() < 2 {
        return Err(PyValueError::new_err("stock axes must have two or more samples"));
    }
    if surface.shape() != [y.len(), x.len()] {
        return Err(PyValueError::new_err("stock grid does not match XY axes"));
    }
    if samples == 0 {
        return Err(PyValueError::new_err("segment needs at least one sample"));
    }
    if !diameter.is_finite()
        || diameter <= 0.0
        || !stock_bottom.is_finite()
        || [angle_deg, tip_diameter, taper_angle_deg, ball_radius]
            .iter()
            .any(|value| !value.is_finite())
        || start.iter().chain(end.iter()).any(|value| !value.is_finite())
    {
        return Err(PyValueError::new_err("non-finite or invalid cutter/motion geometry"));
    }
    if x.windows(2).any(|pair| pair[1] <= pair[0] || !pair[1].is_finite())
        || y.windows(2).any(|pair| pair[1] <= pair[0] || !pair[1].is_finite())
        || !x[0].is_finite()
        || !y[0].is_finite()
    {
        return Err(PyValueError::new_err("stock axes must increase and be finite"));
    }
    let kind = profile_kind(kind)?;
    let radius = diameter / 2.0;
    if (matches!(kind, ProfileKind::Cone) && !(0.0 < angle_deg && angle_deg < 180.0))
        || (matches!(kind, ProfileKind::TaperedBall)
            && (!(0.0 < taper_angle_deg && taper_angle_deg < 90.0)
                || ball_radius <= 0.0
                || ball_radius > radius))
        || (matches!(kind, ProfileKind::Custom)
            && (profile_points.len() < 2
                || profile_points[0].0 != 0.0
                || profile_points
                    .iter()
                    .any(|&(r, z)| !r.is_finite() || !z.is_finite() || r < 0.0 || z < 0.0)
                || profile_points.windows(2).any(|p| p[1].0 <= p[0].0)
                || profile_points[profile_points.len() - 1].0 > radius))
    {
        return Err(PyValueError::new_err("invalid cutter profile parameters"));
    }
    let cutter = CutterProfile {
        kind,
        radius,
        angle_deg,
        tip_radius: tip_diameter / 2.0,
        taper_angle_deg,
        ball_radius,
        points: profile_points,
    };
    let mut grid = surface.as_array_mut();
    let data = grid
        .as_slice_mut()
        .ok_or_else(|| PyValueError::new_err("stock grid must be contiguous"))?;
    Ok(sweep_impl(data, x, y, start, end, samples, stock_bottom, &cutter))
}

#[cfg(test)]
mod tests {
    use super::{sweep_impl, CutterProfile, ProfileKind};

    fn cutter(kind: ProfileKind, radius: f64) -> CutterProfile {
        CutterProfile {
            kind,
            radius,
            angle_deg: 60.0,
            tip_radius: 0.0,
            taper_angle_deg: 10.0,
            ball_radius: 0.5,
            points: vec![(0.0, 0.0), (1.0, 0.5)],
        }
    }

    #[test]
    fn flat_line_removes_expected_cells_and_clamps_to_stock_bottom() {
        let mut surface = vec![0.0; 25];
        let axis = [0.0, 1.0, 2.0, 3.0, 4.0];
        let changed = sweep_impl(
            &mut surface,
            &axis,
            &axis,
            [1.0, 2.0, -2.0],
            [3.0, 2.0, -2.0],
            4,
            -1.5,
            &cutter(ProfileKind::Flat, 0.5),
        );
        assert!(changed >= 3);
        assert_eq!(surface[2 * 5 + 2], -1.5);
        assert_eq!(surface[0], 0.0);
    }

    #[test]
    fn ball_profile_preserves_material_at_outer_edge() {
        let mut surface = vec![0.0; 25];
        let axis = [0.0, 1.0, 2.0, 3.0, 4.0];
        sweep_impl(
            &mut surface,
            &axis,
            &axis,
            [2.0, 2.0, -2.0],
            [2.0, 2.0, -2.0],
            1,
            -5.0,
            &cutter(ProfileKind::Ball, 1.0),
        );
        assert_eq!(surface[2 * 5 + 2], -2.0);
        assert_eq!(surface[2 * 5 + 3], -1.0);
    }
}
