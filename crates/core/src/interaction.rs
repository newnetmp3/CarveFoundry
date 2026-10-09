//! UI-independent hit testing and movement snapping for all CAD objects.
//! Hit test the ORIGINAL pointer press, not the cursor after drag threshold.
use crate::{Point, Project, Curve, polygon_contains};
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PickMode { Objects, Nodes }
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Hit {
    Contour(u64),
    Path(u64),
    Node {path_id:u64,node_id:u64},
    Handle {path_id:u64,segment_id:u64,handle:u8},
}
fn sq(a:Point,b:Point)->f64 {(a.x-b.x).powi(2)+(a.y-b.y).powi(2)}
pub fn segment_distance(p:Point,a:Point,b:Point)->f64 {
    let x=b.x-a.x;let y=b.y-a.y;
    let length=x*x+y*y;
    if length<=1e-15{return sq(p,a).sqrt();}
    let t=(((p.x-a.x)*x+(p.y-a.y)*y)/length).clamp(0.0,1.0);
    sq(p,Point::new(a.x+t*x,a.y+t*y)).sqrt()
}
pub fn pick(project:&Project, point:Point, radius_mm:f64, mode:PickMode)
    ->Option<Hit> {
    if !point.finite() || !radius_mm.is_finite() || radius_mm<=0.0 {
        return None;
    }
    if mode==PickMode::Nodes {
        // Topmost handles/nodes are clickable even when their path was not
        // selected earlier. Selecting an object is NOT a prerequisite.
        let mut best:Option<(f64,Hit)>=None;
        for path in project.paths.iter().rev().filter(|p|p.visible) {
            for node in &path.nodes {
                let world=node.position.offset(path.origin.x,path.origin.y);
                let d=sq(world,point).sqrt();
                if d<=radius_mm && best.as_ref().is_none_or(|(old,_)|d<*old) {
                    best=Some((d,Hit::Node{path_id:path.id,node_id:node.id}));
                }
            }
            for segment in &path.segments {
                if let Curve::Cubic{control1,control2}=segment.curve {
                    for (handle,local) in [(1,control1),(2,control2)] {
                        let d=sq(local.offset(path.origin.x,path.origin.y),point).sqrt();
                        if d<=radius_mm && best.as_ref().is_none_or(|(old,_)|d<*old) {
                            best=Some((d,Hit::Handle{
                                path_id:path.id,segment_id:segment.id,handle,
                            }));
                        }
                    }
                }
            }
        }
        if let Some((_,target))=best{return Some(target);}
    }
    for path in project.paths.iter().rev().filter(|p|p.visible) {
        if let Ok(points)=path.preview_points(0.4)
            && (points.windows(2).any(|edge|
                segment_distance(point,edge[0],edge[1])<=radius_mm)
                || path.closed && polygon_contains(&points,point)) {
            return Some(Hit::Path(path.id));
        }
    }
    for contour in project.contours.iter().rev().filter(|p|p.visible) {
        let pts=contour.world_points();
        if polygon_contains(&pts,point) || pts.iter().enumerate().any(|(i,a)|
            segment_distance(point,*a,pts[(i+1)%pts.len()])<=radius_mm) {
            return Some(Hit::Contour(contour.id));
        }
    }
    None
}
/// Quantize MOVEMENT, never absolute coordinates: no initial snap jump.
pub fn movement_delta(dx:f64,dy:f64,grid:Option<f64>)->Point {
    match grid {
        Some(step) if step.is_finite() && (0.1..=100.0).contains(&step) => {
            Point::new((dx/step).round()*step,(dy/step).round()*step)
        }
        _=>Point::new(dx,dy),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::{AnalyticPath,Primitive};
    fn project()->Project {
        let mut p=Project{next_id:2,..Project::default()};
        p.paths.push(AnalyticPath::preset(1,"Bezier".into(),
            Point::new(20.0,10.0),Primitive::Cubic,40.0,20.0).unwrap());
        p
    }
    #[test]
    fn first_click_hit_node_without_preselection(){
        let p=project();
        assert_eq!(pick(&p,Point::new(20.0,10.0),1.0,PickMode::Nodes),
            Some(Hit::Node{path_id:1,node_id:1}));
    }
    #[test]
    fn first_click_hit_cubic_control_and_object_stroke(){
        let p=project();
        let handle=Point::new(30.0,30.0);
        assert_eq!(pick(&p,handle,0.5,PickMode::Nodes),
            Some(Hit::Handle{path_id:1,segment_id:3,handle:1}));
        assert_eq!(pick(&p,Point::new(20.0,10.0),0.5,PickMode::Objects),
            Some(Hit::Path(1)));
    }
    #[test]
    fn movement_snapping_cannot_shift_initial_anchor(){
        let start=Point::new(12.3,19.7);
        let no_move=movement_delta(0.0,0.0,Some(1.0));
        assert_eq!(start.offset(no_move.x,no_move.y),start);
        assert_eq!(movement_delta(0.3,0.2,None),Point::new(0.3,0.2));
        assert_eq!(movement_delta(1.6,-0.6,Some(1.0)),Point::new(2.0,-1.0));
    }
    #[test]
    fn respects_locked_visibility_and_invalid_pointer(){
        let mut p=project();
        p.paths[0].visible=false;
        assert_eq!(pick(&p,Point::new(20.0,10.0),1.0,PickMode::Nodes),None);
        p.paths[0].visible=true;
        assert_eq!(pick(&p,Point::new(f64::NAN,10.0),1.0,PickMode::Nodes),None);
        // Locked paths can be selected but their edits are refused by Editor.
        p.paths[0].locked=true;
        assert!(matches!(pick(&p,Point::new(20.0,10.0),1.0,PickMode::Nodes),
            Some(Hit::Node{..})));
    }
}
