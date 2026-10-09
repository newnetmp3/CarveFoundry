//! Drag-to-draw placement geometry. A gesture is never an edit until release.
use crate::geometry::Point;
use crate::shapes::ShapeKind;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ShapePlacement {
    pub origin: Point,
    pub width_mm: f64,
    pub height_mm: f64,
}

/// Normalize either diagonal direction to the stock-XY lower-left origin.
/// Circles and Shift-constrained shapes are square. The *movement* delta,
/// not the original start, is snapped by the UI when requested.
pub fn shape_placement(start: Point, delta: Point, kind: ShapeKind, constrain: bool)
    -> Result<ShapePlacement,String> {
    if !start.finite() || !delta.finite() {
        return Err("Drawing gesture contains invalid coordinates".into());
    }
    let mut dx=delta.x;
    let mut dy=delta.y;
    if constrain || kind==ShapeKind::Circle {
        let side=dx.abs().min(dy.abs());
        dx=side.copysign(dx);
        dy=side.copysign(dy);
    }
    let width=dx.abs();
    let height=dy.abs();
    if width<0.1 || height<0.1 {
        return Err("Drag at least 0.1 mm across the stock to create a shape".into());
    }
    if width>10_000.0 || height>10_000.0 {
        return Err("Drawn shape exceeds the 10,000 mm size limit".into());
    }
    let origin=Point::new(start.x.min(start.x+dx),start.y.min(start.y+dy));
    if !origin.finite() || !origin.offset(width,height).finite(){
        return Err("Drawn shape is outside finite design bounds".into());
    }
    Ok(ShapePlacement{origin,width_mm:width,height_mm:height})
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn any_corner_drag_has_consistent_bottom_left_origin() {
        let a=shape_placement(Point::new(10.5,12.25),Point::new(50.0,20.0),
            ShapeKind::Rectangle,false).unwrap();
        let b=shape_placement(Point::new(60.5,32.25),Point::new(-50.0,-20.0),
            ShapeKind::Rectangle,false).unwrap();
        assert_eq!(a,b);
        assert_eq!(a.origin,Point::new(10.5,12.25));
        assert_eq!(a.width_mm,50.0);
        assert_eq!(a.height_mm,20.0);
    }
    #[test]
    fn constrained_rectangles_and_circles_are_square_in_all_directions(){
        let a=shape_placement(Point::new(20.0,20.0),Point::new(-40.0,18.0),
            ShapeKind::Circle,false).unwrap();
        let b=shape_placement(Point::new(20.0,20.0),Point::new(-40.0,18.0),
            ShapeKind::Rectangle,true).unwrap();
        assert_eq!(a,b);
        assert_eq!(a.origin,Point::new(2.0,20.0));
        assert_eq!(a.width_mm,a.height_mm);
        assert_eq!(a.width_mm,18.0);
    }
    #[test]
    fn tiny_invalid_or_unbounded_drags_reject_without_new_geometry(){
        for delta in [Point::new(0.0,0.0),
            Point::new(0.04,12.0),Point::new(f64::NAN,4.0),
            Point::new(500_000.0,2.0)] {
            assert!(shape_placement(Point::new(0.0,0.0),delta,
                ShapeKind::Rectangle,false).is_err());
        }
    }
    #[test]
    fn off_grid_origin_is_never_rounded() {
        let p=shape_placement(Point::new(12.3,14.7),Point::new(30.0,20.0),
            ShapeKind::Ellipse,false).unwrap();
        assert_eq!(p.origin,Point::new(12.3,14.7));
    }
}
