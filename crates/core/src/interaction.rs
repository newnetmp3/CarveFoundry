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
/// Conventional CAD marquee: left-to-right encloses whole vectors;
/// right-to-left crossing selects any overlapping vector bounds.
pub fn marquee_ids(project:&Project,start:Point,end:Point)->Vec<u64>{
    if !start.finite() || !end.finite(){return Vec::new();}
    let (min_x,max_x)=(start.x.min(end.x),start.x.max(end.x));
    let (min_y,max_y)=(start.y.min(end.y),start.y.max(end.y));
    let contain=end.x>=start.x;
    let matches=|points:&[Point]|{
        if points.is_empty(){return false;}
        let lo_x=points.iter().map(|p|p.x).fold(f64::INFINITY,f64::min);
        let hi_x=points.iter().map(|p|p.x).fold(f64::NEG_INFINITY,f64::max);
        let lo_y=points.iter().map(|p|p.y).fold(f64::INFINITY,f64::min);
        let hi_y=points.iter().map(|p|p.y).fold(f64::NEG_INFINITY,f64::max);
        if contain{lo_x>=min_x&&hi_x<=max_x&&lo_y>=min_y&&hi_y<=max_y}
        else{lo_x<=max_x&&hi_x>=min_x&&lo_y<=max_y&&hi_y>=min_y}
    };
    let mut ids=Vec::new();
    for path in project.paths.iter().filter(|p|p.visible){
        if let Ok(points)=path.preview_points(0.35)
            && matches(&points){ids.push(path.id);}
    }
    for contour in project.contours.iter().filter(|p|p.visible){
        if matches(&contour.world_points()){ids.push(contour.id);}
    }
    ids
}

/// Exact CAD reference points, never preview-tessellation vertices.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum SnapKind { Vertex, Midpoint, StockCorner }
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct SnapTarget {
    pub point: Point,
    pub kind: SnapKind,
    pub object_id: Option<u64>,
}
/// Snap to real geometry (not approximation samples) within a screen-space
/// tolerance converted to millimeters by the caller. Exclude the actively
/// edited vector to prevent a dragged node snapping to itself.
pub fn nearest_snap(project:&Project,cursor:Point,radius_mm:f64,
    exclude_ids:&[u64])->Option<SnapTarget>{
    if !cursor.finite() || !radius_mm.is_finite() || radius_mm<=0.0 {
        return None;
    }
    let mut best=None;
    let mut best_dist=radius_mm*radius_mm;
    let mut consider=|p:Point,kind:SnapKind,id:Option<u64>|{
        let d=sq(cursor,p);
        if d<=best_dist && (d<best_dist || best.is_none()) {
            best=Some(SnapTarget{point:p,kind,object_id:id});
            best_dist=d;
        }
    };
    for path in &project.paths{
        if !path.visible || exclude_ids.contains(&path.id){continue;}
        for node in &path.nodes{
            consider(node.position.offset(path.origin.x,path.origin.y),
                SnapKind::Vertex,Some(path.id));
        }
        for (i,segment) in path.segments.iter().enumerate(){
            if !matches!(segment.curve,Curve::Line){continue;}
            let a=path.nodes[i].position;
            let b=path.nodes[(i+1)%path.nodes.len()].position;
            consider(Point::new(path.origin.x+(a.x+b.x)/2.0,
                path.origin.y+(a.y+b.y)/2.0),
                SnapKind::Midpoint,Some(path.id));
        }
    }
    for contour in &project.contours{
        if !contour.visible || exclude_ids.contains(&contour.id){continue;}
        for (i,a) in contour.vertices.iter().enumerate(){
            let b=contour.vertices[(i+1)%contour.vertices.len()];
            consider(a.offset(contour.origin.x,contour.origin.y),
                SnapKind::Vertex,Some(contour.id));
            consider(Point::new(contour.origin.x+(a.x+b.x)/2.0,
                contour.origin.y+(a.y+b.y)/2.0),
                SnapKind::Midpoint,Some(contour.id));
        }
    }
    let stock=&project.stock;
    for p in [Point::new(0.0,0.0),
        Point::new(stock.width_mm,0.0),
        Point::new(0.0,stock.height_mm),
        Point::new(stock.width_mm,stock.height_mm)] {
        consider(p,SnapKind::StockCorner,None);
    }
    best
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
    fn selection_marquee_enclosure_vs_crossing_and_hidden(){
        let mut p=project();
        p.paths.push(AnalyticPath::preset(2,"Line".into(),
            Point::new(80.0,40.0),Primitive::Line,40.0,10.0).unwrap());
        p.next_id=3;
        assert_eq!(marquee_ids(&p,Point::new(70.0,30.0),
            Point::new(130.0,50.0)),vec![2]);
        assert_eq!(marquee_ids(&p,Point::new(85.0,50.0),
            Point::new(75.0,30.0)),vec![2]);
        assert!(marquee_ids(&p,Point::new(85.0,30.0),
            Point::new(95.0,50.0)).is_empty());
        p.paths[1].visible=false;
        assert!(marquee_ids(&p,Point::new(130.0,55.0),
            Point::new(70.0,30.0)).is_empty());
    }
    #[test]
    fn exact_geometry_snaps_to_nodes_and_line_midpoints(){
        let mut p=project();
        p.paths.push(AnalyticPath::preset(2,"Straight".into(),
            Point::new(80.0,50.0),Primitive::Line,30.0,10.0).unwrap());
        p.next_id=3;
        assert_eq!(nearest_snap(&p,Point::new(80.2,50.1),1.0,&[]),
            Some(SnapTarget{
                point:Point::new(80.0,50.0),
                kind:SnapKind::Vertex,object_id:Some(2)}));
        assert_eq!(nearest_snap(&p,Point::new(94.6,50.0),1.0,&[]),
            Some(SnapTarget{
                point:Point::new(95.0,50.0),
                kind:SnapKind::Midpoint,object_id:Some(2)}));
        assert!(nearest_snap(&p,Point::new(95.0,50.0),1.0,&[2]).is_none());
    }
    #[test]
    fn snapping_stock_corners_and_visibility_is_deterministic(){
        let mut p=project();
        p.paths[0].visible=false;
        assert_eq!(nearest_snap(&p,Point::new(0.1,0.1),1.0,&[]),
            Some(SnapTarget{point:Point::new(0.0,0.0),
                kind:SnapKind::StockCorner,object_id:None}));
        assert!(nearest_snap(&p,Point::new(20.0,10.0),1.0,&[]).is_none());
        assert!(nearest_snap(&p,Point::new(f64::NAN,0.0),1.0,&[]).is_none());
        assert!(nearest_snap(&p,Point::new(5.0,5.0),0.0,&[]).is_none());
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
