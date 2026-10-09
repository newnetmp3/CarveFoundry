//! CAD shape constructors backed by editable analytic line/cubic segments.
use crate::{AnalyticPath,Curve,PathNode,PathSegment,Point};
use std::f64::consts::{PI,TAU};
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum ShapeKind {Rectangle,Triangle,Pentagon,Hexagon,Octagon,Star,Circle,Ellipse}
impl ShapeKind {
    pub fn title(self)->&'static str {
        match self {
            Self::Rectangle=>"Rectangle",Self::Triangle=>"Triangle",
            Self::Pentagon=>"Pentagon",Self::Hexagon=>"Hexagon",
            Self::Octagon=>"Octagon",Self::Star=>"Star",
            Self::Circle=>"Circle",Self::Ellipse=>"Ellipse",
        }
    }
}
pub fn polyline(id:u64,name:String,origin:Point,points:Vec<Point>,
    closed:bool)->Result<AnalyticPath,String> {
    if points.len()<2 || points.len()>256 || (closed && points.len()<3) {
        return Err("A path must have 2–256 nodes (3+ when closed)".into());
    }
    let count=points.len();
    let segment_count=if closed{count}else{count-1};
    let next_id=(count+segment_count+1) as u64;
    let path=AnalyticPath {
        id,name,origin,visible:true,locked:false,closed,
        nodes:points.into_iter().enumerate().map(|(i,position)|
            PathNode{id:i as u64+1,position}).collect(),
        segments:(0..segment_count).map(|i|PathSegment{
            id:count as u64+i as u64+1,curve:Curve::Line,
        }).collect(),
        next_element_id:next_id,
    };
    path.validate()?;
    Ok(path)
}
pub fn create_shape(id:u64,name:String,origin:Point,kind:ShapeKind,
    width:f64,height:f64)->Result<AnalyticPath,String> {
    if !width.is_finite() || !height.is_finite()
        || !(0.1..=10_000.0).contains(&width) || !(0.1..=10_000.0).contains(&height) {
        return Err("Shape dimensions must be between 0.1 and 10,000 mm".into());
    }
    if matches!(kind,ShapeKind::Circle|ShapeKind::Ellipse) {
        let x=width/2.0;let y=height/2.0;
        let k=0.552_284_749_830_793_6;
        let mut path=polyline(id,name,origin,vec![
            Point::new(width,y),Point::new(x,height),
            Point::new(0.0,y),Point::new(x,0.0),
        ],true)?;
        let controls=[
            (Point::new(width,y+k*y),Point::new(x+k*x,height)),
            (Point::new(x-k*x,height),Point::new(0.0,y+k*y)),
            (Point::new(0.0,y-k*y),Point::new(x-k*x,0.0)),
            (Point::new(x+k*x,0.0),Point::new(width,y-k*y)),
        ];
        for (segment,(control1,control2)) in path.segments.iter_mut().zip(controls){
            segment.curve=Curve::Cubic{control1,control2};
        }
        path.validate()?;
        return Ok(path);
    }
    if kind==ShapeKind::Rectangle {
        return polyline(id,name,origin,vec![
            Point::new(0.0,0.0),Point::new(width,0.0),
            Point::new(width,height),Point::new(0.0,height),
        ],true);
    }
    let corners=match kind {
        ShapeKind::Triangle=>3,ShapeKind::Pentagon=>5,
        ShapeKind::Hexagon=>6,ShapeKind::Octagon=>8,
        ShapeKind::Star=>10,_=>unreachable!(),
    };
    let vertices=(0..corners).map(|i| {
        let angle=-PI/2.0+(i as f64)*TAU/(corners as f64);
        let factor=if kind==ShapeKind::Star && i%2==1 {0.45} else{1.0};
        Point::new(width/2.0+factor*width/2.0*angle.cos(),
            height/2.0+factor*height/2.0*angle.sin())
    }).collect();
    polyline(id,name,origin,vertices,true)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn all_shapes_are_closed_editable_analytic_paths(){
        for kind in [ShapeKind::Rectangle,ShapeKind::Triangle,
            ShapeKind::Pentagon,ShapeKind::Hexagon,ShapeKind::Octagon,
            ShapeKind::Star,ShapeKind::Circle,ShapeKind::Ellipse] {
            let p=create_shape(1,kind.title().into(),Point::new(10.0,10.0),
                kind,80.0,60.0).unwrap();
            assert!(p.closed);
            assert_eq!(p.nodes.len(),p.segments.len());
            assert!(p.validate().is_ok());
            assert!(p.preview_points(0.2).unwrap().len()>2);
        }
    }
    #[test]
    fn circles_remain_four_cubics_not_flattened_polylines() {
        let p=create_shape(1,"Circle".into(),Point::new(0.0,0.0),
            ShapeKind::Circle,50.0,50.0).unwrap();
        assert_eq!(p.nodes.len(),4);
        assert!(p.segments.iter().all(|s|matches!(s.curve,Curve::Cubic{..})));
    }
    #[test]
    fn validates_polyline_geometry_early(){
        assert!(polyline(1,"Too short".into(),Point::new(0.0,0.0),
            vec![Point::new(0.0,0.0)],false).is_err());
        assert!(create_shape(1,"Bad".into(),Point::new(0.0,0.0),
            ShapeKind::Rectangle,-5.0,20.0).is_err());
    }
}
