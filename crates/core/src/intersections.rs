//! Source-faithful line, circular arc, and cubic Bézier intersections.
//! All crossing candidates derive from retained analytic geometry.
//! Overlapping coincident curves and unresolvable pairs fail closed.
use crate::{AnalyticPath,Curve,Point,Project};
use std::f64::consts::TAU;

const EPS:f64=1e-8;
const MAX_HITS:usize=128;
const MAX_PAIRS:usize=150_000;
fn add(a:Point,b:Point)->Point{Point::new(a.x+b.x,a.y+b.y)}
fn sub(a:Point,b:Point)->Point{Point::new(a.x-b.x,a.y-b.y)}
fn mul(a:Point,x:f64)->Point{Point::new(a.x*x,a.y*x)}
fn dot(a:Point,b:Point)->f64{a.x*b.x+a.y*b.y}
fn cross(a:Point,b:Point)->f64{a.x*b.y-a.y*b.x}
fn norm(a:Point)->f64{a.x.hypot(a.y)}
fn dist(a:Point,b:Point)->f64{norm(sub(a,b))}

#[derive(Clone,Debug,PartialEq)]
pub struct IntersectionHit{
    pub source_path_id:u64,
    pub source_segment_id:u64,
    pub target_path_id:u64,
    pub target_segment_id:u64,
    pub source_t:f64,
    pub target_t:f64,
    pub position:Point,
}
#[derive(Clone,Debug,Default)]
pub struct IntersectionScan{
    pub hits:Vec<IntersectionHit>,
    /// Coincident / unresolved overlapping edge pairs are never silently accepted.
    pub unsupported_pairs:usize,
}
#[derive(Clone,Copy)]
struct Edge{
    a:Point,b:Point,curve:Curve,
}
impl Edge{
    fn in_world(p:&AnalyticPath,index:usize)->Self{
        let world=|q:Point|q.offset(p.origin.x,p.origin.y);
        let curve=match p.segments[index].curve{
            Curve::Line=>Curve::Line,
            Curve::Arc{center,clockwise}=>Curve::Arc{
                center:world(center),clockwise,
            },
            Curve::Cubic{control1,control2}=>Curve::Cubic{
                control1:world(control1),control2:world(control2)
            },
        };
        Self{a:world(p.nodes[index].position),
            b:world(p.nodes[(index+1)%p.nodes.len()].position),curve}
    }
}
fn in_unit(t:f64)->bool{t.is_finite()&&(-EPS..=1.0+EPS).contains(&t)}
fn angle_param(a:Point,b:Point,center:Point,clockwise:bool,p:Point)->Option<f64>{
    let r=dist(a,center);
    if r<EPS|| (dist(p,center)-r).abs()>r.max(1.0)*2e-7 {
        return None;
    }
    let start=(a.y-center.y).atan2(a.x-center.x);
    let end=(b.y-center.y).atan2(b.x-center.x);
    let query=(p.y-center.y).atan2(p.x-center.x);
    let sweep=if clockwise{
        (start-end).rem_euclid(TAU)
    }else{(end-start).rem_euclid(TAU)};
    if sweep<EPS{return None;}
    let along=if clockwise{
        (start-query).rem_euclid(TAU)
    }else{(query-start).rem_euclid(TAU)};
    if along>sweep+1e-7{return None;}
    Some((along/sweep).clamp(0.0,1.0))
}
fn line_line(a:Edge,b:Edge)->Vec<(Point,f64,f64)>{
    let u=sub(a.b,a.a);let v=sub(b.b,b.a);
    let den=cross(u,v);
    if den.abs()<1e-12*norm(u).max(1.0)*norm(v).max(1.0){
        return vec![];
    }
    let delta=sub(b.a,a.a);
    let t=cross(delta,v)/den;
    let s=cross(delta,u)/den;
    if !in_unit(t)||!in_unit(s){return vec![];}
    vec![(add(a.a,mul(u,t)),t.clamp(0.0,1.0),s.clamp(0.0,1.0))]
}
fn line_arc(line:Edge,arc:Edge)->Vec<(Point,f64,f64)>{
    let Curve::Arc{center,clockwise}=arc.curve else{return vec![];};
    let d=sub(line.b,line.a);
    let radius=dist(arc.a,center);
    let delta=sub(line.a,center);
    let aa=dot(d,d);
    if aa<EPS*EPS {return vec![];}
    let bb=2.0*dot(delta,d);
    let cc=dot(delta,delta)-radius*radius;
    let discriminant=bb*bb-4.0*aa*cc;
    let fuzz=(bb*bb+4.0*aa*cc.abs()).max(1.0)*1e-12;
    if discriminant< -fuzz{return vec![];}
    let root=discriminant.max(0.0).sqrt();
    let ts=[(-bb-root)/(2.0*aa),(-bb+root)/(2.0*aa)];
    let mut result:Vec<(Point,f64,f64)>=Vec::new();
    for t in ts{
        if !in_unit(t){continue;}
        let t=t.clamp(0.0,1.0);
        let p=add(line.a,mul(d,t));
        if let Some(s)=angle_param(arc.a,arc.b,center,clockwise,p)
            && result.iter().all(|(other,..)|dist(p,*other)>1e-7){
            result.push((p,t,s));
        }
    }
    result
}
fn arc_arc(a:Edge,b:Edge)->Vec<(Point,f64,f64)>{
    let (Curve::Arc{center:c1,clockwise:w1},
        Curve::Arc{center:c2,clockwise:w2})=(a.curve,b.curve)
        else{return vec![];};
    let d=dist(c1,c2);
    let r1=dist(a.a,c1);let r2=dist(b.a,c2);
    if d<EPS || d>r1+r2+EPS||d<(r1-r2).abs()-EPS{return vec![];}
    let direction=mul(sub(c2,c1),1.0/d);
    let x=(r1*r1-r2*r2+d*d)/(2.0*d);
    let height2=r1*r1-x*x;
    if height2< -(r1*r1).max(1.0)*1e-10{return vec![];}
    let center=add(c1,mul(direction,x));
    let perp=Point::new(-direction.y,direction.x);
    let h=height2.max(0.0).sqrt();
    let mut found:Vec<(Point,f64,f64)>=Vec::new();
    for sign in [1.0,-1.0]{
        let p=add(center,mul(perp,h*sign));
        if let (Some(t),Some(u))=(
            angle_param(a.a,a.b,c1,w1,p),angle_param(b.a,b.b,c2,w2,p))
            && found.iter().all(|(q,..)|dist(*q,p)>1e-7){
            found.push((p,t,u));
        }
    }
    found
}
fn intersect(a:Edge,b:Edge)->(Vec<(Point,f64,f64)>,bool){
    match (a.curve,b.curve){
        (Curve::Line,Curve::Line)=>(line_line(a,b),false),
        (Curve::Line,Curve::Arc{..})=>(line_arc(a,b),false),
        (Curve::Arc{..},Curve::Line)=>{
            (line_arc(b,a).into_iter().map(|(p,u,t)|(p,t,u)).collect(),false)
        },
        (Curve::Arc{center:c1,..},Curve::Arc{center:c2,..})=>{
            if dist(c1,c2)<EPS{return (vec![],true);}
            (arc_arc(a,b),false)
        },
        (Curve::Cubic{control1,control2},Curve::Line)=>{
            crate::bezier_intersections::cubic_line(
                [a.a,control1,control2,a.b],b.a,b.b)
        },
        (Curve::Line,Curve::Cubic{control1,control2})=>{
            let (hits,unsupported)=crate::bezier_intersections::cubic_line(
                [b.a,control1,control2,b.b],a.a,a.b);
            (hits.into_iter().map(|(p,t,u)|(p,u,t)).collect(),unsupported)
        },
        (Curve::Cubic{control1,control2},
            Curve::Arc{center,clockwise})=>{
            crate::bezier_intersections::cubic_arc(
                [a.a,control1,control2,a.b],b.a,b.b,center,clockwise)
        },
        (Curve::Arc{center,clockwise},
            Curve::Cubic{control1,control2})=>{
            let (hits,unsupported)=crate::bezier_intersections::cubic_arc(
                [b.a,control1,control2,b.b],a.a,a.b,center,clockwise);
            (hits.into_iter().map(|(p,t,u)|(p,u,t)).collect(),unsupported)
        },
        (Curve::Cubic{control1:a1,control2:a2},
            Curve::Cubic{control1:b1,control2:b2})=>{
            crate::bezier_intersections::cubic_cubic(
                [a.a,a1,a2,a.b],[b.a,b1,b2,b.b])
        },
    }
}
pub fn segment_crossings(source:&AnalyticPath,source_segment_id:u64,
    target:&AnalyticPath,target_segment_id:u64)->Result<(Vec<IntersectionHit>,bool),String>{
    if source.id==target.id {
        return Err("Choose a different reference vector for intersections".into());
    }
    let i=source.segments.iter().position(|s|s.id==source_segment_id)
        .ok_or("Selected source edge no longer exists")?;
    let j=target.segments.iter().position(|s|s.id==target_segment_id)
        .ok_or("Reference edge no longer exists")?;
    let (matches,unsupported)=intersect(Edge::in_world(source,i),Edge::in_world(target,j));
    let hits=matches.into_iter().filter(|(_,t,_)|
        (0.0001..=0.9999).contains(t))
        .map(|(position,source_t,target_t)|IntersectionHit{
            source_path_id:source.id,source_segment_id,
            target_path_id:target.id,target_segment_id,
            source_t,target_t,position,
        }).collect();
    Ok((hits,unsupported))
}
/// Deliberately evaluated ON DEMAND by the UI, never for each rendered frame.
pub fn find_intersections(project:&Project,source_path_id:u64)
    ->Result<IntersectionScan,String>{
    let source=project.paths.iter().find(|p|p.id==source_path_id)
        .ok_or("Select an analytic source vector")?;
    if !project.editable_vector(source_path_id) {
        return Err("Source vector is hidden or locked".into());
    }
    let mut result=IntersectionScan::default();
    let mut pairs=0usize;
    for target in project.paths.iter().filter(|p|
        p.id!=source_path_id && project.effective_visible(p.id)){
        for segment in &source.segments{
            for other in &target.segments{
                pairs+=1;
                if pairs>MAX_PAIRS{
                    return Err("Too many geometry pairs to scan; hide unrelated vectors".into());
                }
                let (hits,unsupported)=
                    segment_crossings(source,segment.id,target,other.id)?;
                if unsupported{result.unsupported_pairs+=1;}
                for hit in hits {
                    if result.hits.iter().any(|h|
                        h.source_segment_id==hit.source_segment_id &&
                        dist(h.position,hit.position)<1e-7){continue;}
                    if result.hits.len()>=MAX_HITS {
                        return Err("More than 128 crossings; isolate fewer vectors".into());
                    }
                    result.hits.push(hit);
                }
            }
        }
    }
    result.hits.sort_by(|a,b|{
        (a.source_segment_id,a.source_t,a.target_path_id)
            .partial_cmp(&(b.source_segment_id,b.source_t,b.target_path_id))
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    Ok(result)
}
pub fn select_verified(project:&Project,hit:&IntersectionHit)->Result<IntersectionHit,String>{
    if !project.editable_vector(hit.source_path_id){
        return Err("Source vector became hidden/locked".into());
    }
    if !project.effective_visible(hit.target_path_id){
        return Err("Reference vector is now hidden".into());
    }
    let a=project.paths.iter().find(|p|p.id==hit.source_path_id)
        .ok_or("Source vector no longer exists")?;
    let b=project.paths.iter().find(|p|p.id==hit.target_path_id)
        .ok_or("Reference vector no longer exists")?;
    let (current,unsupported)=segment_crossings(
        a,hit.source_segment_id,b,hit.target_segment_id)?;
    if unsupported{return Err("Selected curve pair is not supported".into());}
    current.into_iter().find(|now|
        dist(now.position,hit.position)<0.0001
        && (now.source_t-hit.source_t).abs()<1e-6)
        .ok_or_else(||"Crossing moved; scan again before editing".into())
}
#[cfg(test)]
mod tests{
    use super::*;
    use crate::{Primitive,shapes::polyline};
    fn segment(id:u64,a:Point,b:Point)->AnalyticPath{
        polyline(id,"Line".into(),Point::new(0.0,0.0),vec![a,b],false).unwrap()
    }
    #[test]
    fn perpendicular_lines_have_true_analytic_fraction(){
        let a=segment(1,Point::new(0.0,0.0),Point::new(10.0,0.0));
        let b=segment(2,Point::new(3.0,-10.0),Point::new(3.0,10.0));
        let (hits,unsupported)=segment_crossings(&a,3,&b,3).unwrap();
        assert!(!unsupported);
        assert_eq!(hits.len(),1);
        assert!((hits[0].source_t-0.3).abs()<1e-9);
        assert!((hits[0].position.x-3.0).abs()<1e-9);
        assert!(segment_crossings(&b,3,&a,3).is_ok());
    }
    #[test]
    fn line_arc_crossings_are_bounded_to_real_arc_sweep(){
        // Bottom semicircle: start left, end right, positive clockwise sweep.
        let mut arc=crate::AnalyticPath::preset(2,"Circle arc".into(),
            Point::new(0.0,0.0),Primitive::Arc,10.0,6.0).unwrap();
        arc.segments[0].curve=Curve::Arc{center:Point::new(5.0,0.0),clockwise:true};
        let l=segment(1,Point::new(5.0,-8.0),Point::new(5.0,8.0));
        let (hits,_)=segment_crossings(&l,3,&arc,3).unwrap();
        assert_eq!(hits.len(),1);
        assert!((hits[0].position.y-5.0).abs()<1e-8);
        // Reverse reference: same crossing preserved with switched fractions.
        let (reversed,_)=segment_crossings(&arc,3,&l,3).unwrap();
        assert_eq!(reversed.len(),1);
    }
    #[test]
    fn arc_arc_circle_geometry_and_cubic_intersections(){
        let mut a=crate::AnalyticPath::preset(1,"Arc A".into(),
            Point::new(0.0,0.0),Primitive::Arc,10.0,6.0).unwrap();
        let mut b=a.clone();b.id=2;
        b.origin=Point::new(5.0,0.0);
        // Arc A and B are both upper semicircles, one crossing in upper half.
        let (hits,_)=segment_crossings(&a,3,&b,3).unwrap();
        assert_eq!(hits.len(),1);
        assert!(hits[0].position.y>0.0);
        a.segments[0].curve=Curve::Cubic{
            control1:Point::new(2.0,5.0),
            control2:Point::new(8.0,5.0)};
        let (crossings,flag)=segment_crossings(&a,3,&b,3).unwrap();
        assert!(!flag,"cubic-to-true-circle must be supported");
        assert!(crossings.iter().all(|h|h.position.finite()));
    }
    #[test]
    fn screenshot_regression_closed_polygon_crosses_curved_blue_bezier(){
        let mut p=crate::shapes::polyline(1,"Five edges".into(),
            Point::new(0.0,0.0),
            vec![Point::new(70.0,70.0),Point::new(110.0,45.0),
                Point::new(150.0,70.0),Point::new(140.0,115.0),
                Point::new(80.0,115.0)],true).unwrap();
        let mut curve=crate::AnalyticPath::preset(2,"Blue curve".into(),
            Point::new(0.0,0.0),Primitive::Cubic,90.0,140.0).unwrap();
        curve.nodes[0].position=Point::new(65.0,35.0);
        curve.nodes[1].position=Point::new(160.0,145.0);
        curve.segments[0].curve=Curve::Cubic{
            control1:Point::new(90.0,110.0),
            control2:Point::new(150.0,165.0),
        };
        p.validate().unwrap();curve.validate().unwrap();
        let mut project=Project::default();
        project.paths.extend([p,curve]);
        project.next_id=3;
        project.validate().unwrap();
        let scan=find_intersections(&project,1).unwrap();
        assert_eq!(scan.unsupported_pairs,0,"cubic crossings should be supported");
        assert!(scan.hits.len()>=2,"expected multiple curve/polygon crossings: {:?}",scan.hits);
        for hit in scan.hits {
            let verified=select_verified(&project,&hit).unwrap();
            assert!((verified.source_t-hit.source_t).abs()<1e-7);
        }
    }
    #[test]
    fn asymmetric_cubic_line_and_cubic_cubic_preserve_parameter_order(){
        let mut curve=crate::AnalyticPath::preset(1,"Cubic".into(),
            Point::new(20.0,15.0),Primitive::Cubic,10.0,10.0).unwrap();
        curve.segments[0].curve=Curve::Cubic{
            control1:Point::new(0.0,10.0),control2:Point::new(10.0,10.0)
        };
        let straight=segment(2,Point::new(15.0,20.0),Point::new(35.0,20.0));
        let (a,failed)=segment_crossings(&curve,3,&straight,3).unwrap();
        assert!(!failed);assert_eq!(a.len(),2);
        let (b,failed)=segment_crossings(&straight,3,&curve,3).unwrap();
        assert!(!failed);assert_eq!(b.len(),2);
        for h in &a{
            assert!(b.iter().any(|v|dist(h.position,v.position)<1e-7
                &&(v.target_t-h.source_t).abs()<1e-7
                &&(v.source_t-h.target_t).abs()<1e-7));
        }
        let mut other=straight;
        other.segments[0].curve=Curve::Cubic{
            control1:Point::new(20.0,20.0),
            control2:Point::new(30.0,20.0),
        };
        let (hits,failed)=segment_crossings(&curve,3,&other,3).unwrap();
        assert!(!failed);assert_eq!(hits.len(),2);
    }
    #[test]
    fn on_demand_scan_ignores_hidden_and_revalidates_edit(){
        let mut project=Project::default();
        project.paths.push(segment(1,Point::new(0.0,0.0),Point::new(10.0,0.0)));
        project.paths.push(segment(2,Point::new(4.0,-5.0),Point::new(4.0,5.0)));
        project.next_id=3;project.validate().unwrap();
        let scan=find_intersections(&project,1).unwrap();
        assert_eq!(scan.hits.len(),1);
        let verified=select_verified(&project,&scan.hits[0]).unwrap();
        assert_eq!(scan.hits[0],verified);
        project.paths[1].origin.x=2.0;
        assert!(select_verified(&project,&scan.hits[0]).is_err());
        project.paths[1].visible=false;
        assert!(find_intersections(&project,1).unwrap().hits.is_empty());
    }
}
