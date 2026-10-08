//! Stock-origin grid precision for native Rust Studio design placements.
//!
//! All coordinates remain millimetres from the lower-left stock origin.
//! The pure functions never edit source CF3D, cutter motion or fixtures.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GridSettings {
    pub enabled: bool,
    pub step_mm: f64,
}

impl Default for GridSettings {
    fn default() -> Self {
        Self { enabled: false, step_mm: 1.0 }
    }
}

impl GridSettings {
    pub fn validate(self) -> Result<(), String> {
        if !self.step_mm.is_finite() || !(0.05..=100.0).contains(&self.step_mm) {
            return Err("Grid spacing must be finite, from 0.05 to 100 mm".into());
        }
        Ok(())
    }

    /// Return the endpoint for an absolute drag displacement from its original
    /// position, not a succession of rounded per-frame deltas. This preserves
    /// sub-grid movement until a full grid interval has been reached.
    pub fn target(
        self,
        anchor: [f64; 2],
        displacement: [f64; 2],
    ) -> Result<[f64; 2], String> {
        self.validate()?;
        if anchor.into_iter().chain(displacement).any(|v| !v.is_finite() || v.abs() > 100_000.0) {
            return Err("Placement coordinates and drag offsets must be finite within 100,000 mm".into());
        }
        let moved = [anchor[0] + displacement[0], anchor[1] + displacement[1]];
        if moved.into_iter().any(|v| !v.is_finite() || v.abs() > 100_000.0) {
            return Err("Target position exceeds the 100,000 mm placement bound".into());
        }
        if !self.enabled { return Ok(moved); }
        // Round against absolute (0,0) in stock XY, not viewport pan or screen
        // origin. Avoid negative zero in output and CF3D translation deltas.
        let snapped = moved.map(|v| {
            let result = (v / self.step_mm).round() * self.step_mm;
            if result == 0.0 { 0.0 } else { result }
        });
        if snapped.into_iter().any(|v| !v.is_finite() || v.abs() > 100_000.0) {
            return Err("Grid-aligned placement exceeds the safe coordinate range".into());
        }
        Ok(snapped)
    }

    pub fn align(self, xy: [f64; 2]) -> Result<[f64; 2], String> {
        self.target(xy, [0.0, 0.0])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stock_origin_grid_aligns_positive_and_negative_positions() {
        let grid = GridSettings { enabled: true, step_mm: 2.0 };
        assert_eq!(grid.align([7.01, 5.0]).unwrap(), [8.0, 6.0]);
        assert_eq!(grid.align([-5.0, -1.99]).unwrap(), [-6.0, -2.0]);
        assert_eq!(grid.align([-0.1, 0.1]).unwrap(), [0.0, 0.0]);
    }

    #[test]
    fn drag_is_absolute_from_anchor_without_fractional_delta_loss() {
        let grid = GridSettings { enabled: true, step_mm: 1.0 };
        let origin = [10.0, 20.0];
        assert_eq!(grid.target(origin, [0.2, -0.1]).unwrap(), origin);
        assert_eq!(grid.target(origin, [0.4, -0.1]).unwrap(), origin);
        assert_eq!(grid.target(origin, [0.6, -0.6]).unwrap(), [11.0, 19.0]);
        assert_eq!(grid.target(origin, [1.2, -1.3]).unwrap(), [11.0, 19.0]);
    }

    #[test]
    fn toggle_keeps_exact_ungrounded_design_positions() {
        let grid = GridSettings::default();
        let original = [3.15, 9.26];
        assert_eq!(grid.align(original).unwrap(), original);
        let result = grid.target(original, [0.11, 0.22]).unwrap();
        assert!((result[0] - 3.26).abs() < 1e-10);
        assert!((result[1] - 9.48).abs() < 1e-10);
    }

    #[test]
    fn rejects_bad_pitch_and_nonfinite_or_overflowing_targets() {
        for value in [0.0, -1.0, f64::NAN, f64::INFINITY, 100.1] {
            assert!(GridSettings { enabled: true, step_mm: value }.validate().is_err());
        }
        let snap = GridSettings { enabled: true, step_mm: 0.05 };
        assert!(snap.target([f64::NAN, 1.0], [0.0, 0.0]).is_err());
        assert!(snap.target([10.0, 20.0], [f64::INFINITY, 0.0]).is_err());
        assert!(snap.target([99_999.0, 1.0], [5.0, 0.0]).is_err());
    }
}
