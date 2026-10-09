//! Pure, finite, 2D geometry. All distances are mm from stock-bottom-left XY0.
use serde::{Deserialize, Serialize};

const EPS: f64 = 1e-9;

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}
impl Point {
    pub const fn new(x: f64, y: f64) -> Self { Self { x, y } }
    pub fn offset(self, x: f64, y: f64) -> Self {
        Self::new(self.x + x, self.y + y)
    }
    pub fn finite(self) -> bool {
        self.x.is_finite() && self.y.is_finite()
            && self.x.abs() <= 100_000.0 && self.y.abs() <= 100_000.0
    }
}

pub fn signed_area(points: &[Point]) -> f64 {
    if points.len() < 3 { return 0.0; }
    let mut sum = 0.0;
    for i in 0..points.len() {
        let a = points[i];
        let b = points[(i + 1) % points.len()];
        sum += a.x * b.y - b.x * a.y;
    }
    sum * 0.5
}

fn cross(a: Point, b: Point, c: Point) -> f64 {
    (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
}
fn touches(p: Point, a: Point, b: Point) -> bool {
    cross(a,b,p).abs() <= EPS
        && p.x >= a.x.min(b.x) - EPS && p.x <= a.x.max(b.x) + EPS
        && p.y >= a.y.min(b.y) - EPS && p.y <= a.y.max(b.y) + EPS
}
fn edges_intersect(a: Point, b: Point, c: Point, d: Point) -> bool {
    let ab_c = cross(a,b,c);
    let ab_d = cross(a,b,d);
    let cd_a = cross(c,d,a);
    let cd_b = cross(c,d,b);
    ((ab_c > EPS && ab_d < -EPS || ab_c < -EPS && ab_d > EPS)
        && (cd_a > EPS && cd_b < -EPS || cd_a < -EPS && cd_b > EPS))
        || touches(c,a,b) || touches(d,a,b) || touches(a,c,d) || touches(b,c,d)
}

/// A contour is a simple closed polygon, never a sampled substitute for a
/// persisted analytic curve. Arcs and cubics will have first-class types later.
pub fn validate_polygon(points: &[Point]) -> Result<(), String> {
    if !(3..=4096).contains(&points.len()) {
        return Err("A closed contour needs 3–4096 vertices".into());
    }
    if points.iter().any(|p| !p.finite()) {
        return Err("Contour contains nonfinite or out-of-range coordinates".into());
    }
    let n=points.len();
    for i in 0..n {
        let a=points[i];
        let b=points[(i+1)%n];
        if (a.x-b.x).hypot(a.y-b.y) <= EPS {
            return Err("Contour has a zero-length edge".into());
        }
        for j in (i+1)..n {
            if j==i+1 || (i==0 && j==n-1) { continue; }
            if edges_intersect(a,b,points[j],points[(j+1)%n]) {
                return Err("Contour contains intersecting or touching nonadjacent edges".into());
            }
        }
    }
    if signed_area(points).abs() <= EPS {
        return Err("Contour area is zero".into());
    }
    Ok(())
}

/// Even/odd hit testing, including polygon outline.
pub fn polygon_contains(points: &[Point], query: Point) -> bool {
    if points.len()<3 || !query.finite() { return false; }
    let mut inside=false;
    for i in 0..points.len() {
        let a=points[i];
        let b=points[(i+1)%points.len()];
        if touches(query,a,b) { return true; }
        if (a.y>query.y)!=(b.y>query.y) {
            let x=a.x+(query.y-a.y)*(b.x-a.x)/(b.y-a.y);
            if query.x<x { inside=!inside; }
        }
    }
    inside
}
#[cfg(test)]
mod tests {
    use super::*;
    fn square() -> Vec<Point> {
        vec![Point::new(0.,0.),Point::new(10.,0.),
            Point::new(10.,10.),Point::new(0.,10.)]
    }
    #[test]
    fn valid_simple_contour_and_hit_test() {
        let p=square();
        validate_polygon(&p).unwrap();
        assert_eq!(signed_area(&p),100.);
        assert!(polygon_contains(&p,Point::new(5.,5.)));
        assert!(polygon_contains(&p,Point::new(0.,5.)));
        assert!(!polygon_contains(&p,Point::new(15.,5.)));
    }
    #[test]
    fn invalid_crossing_touch_and_nan_fail_closed() {
        let p=vec![Point::new(0.,0.),Point::new(5.,5.),
            Point::new(0.,5.),Point::new(5.,0.)];
        assert!(validate_polygon(&p).is_err());
        let mut p=square();
        p[1].x=f64::NAN;
        assert!(validate_polygon(&p).is_err());
        let mut p=square();
        p[1]=p[0];
        assert!(validate_polygon(&p).is_err());
    }
    #[test]
    fn concave_shape_is_valid() {
        let p=vec![Point::new(0.,0.),Point::new(10.,0.),
          Point::new(10.,3.),Point::new(3.,3.),
          Point::new(3.,10.),Point::new(0.,10.)];
        validate_polygon(&p).unwrap();
        assert!(!polygon_contains(&p,Point::new(7.,7.)));
    }
}
