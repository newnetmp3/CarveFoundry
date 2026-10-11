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
/// Cover the geometry of a true circular sweep using at most two
/// non-wrapping CCW intervals on [0, 2*pi]. Winding changes traversal
/// direction, not which points of the source circle are occupied.
fn arc_angular_intervals(edge:Edge)->Vec<(f64,f64)>{
    let Curve::Arc{center,clockwise}=edge.curve else {return vec![];};
    let a=sub(edge.a,center);
    let b=sub(edge.b,center);
    let begin=a.y.atan2(a.x).rem_euclid(TAU);
    let end=b.y.atan2(b.x).rem_euclid(TAU);
    let start=if clockwise{end}else{begin};
    let sweep=if clockwise{(begin-end).rem_euclid(TAU)}
        else{(end-begin).rem_euclid(TAU)};
    let finish=start+sweep;
    if finish<=TAU{
        vec![(start,finish)]
    }else{
        vec![(start,TAU),(0.0,finish-TAU)]
    }
}
fn on_arc_parameter(edge:Edge,p:Point)->Option<f64>{
    let Curve::Arc{center,clockwise}=edge.curve else{return None;};
    // Preserve exact terminal parameters across the angular wrap seam.
    if dist(p,edge.a)<1e-7{return Some(0.0);}
    if dist(p,edge.b)<1e-7{return Some(1.0);}
    angle_param(edge.a,edge.b,center,clockwise,p)
}
/// Distinguish distinct concentric radii from overlapping coincident
/// circular *sweeps*. Isolated endpoint contacts are retained as real
/// intersections; nonzero common angular length is never accepted as
/// a single well-defined intersection.
fn coincident_arc_pair(a:Edge,b:Edge)->(Vec<(Point,f64,f64)>,bool){
    let (Curve::Arc{center:c1,..},Curve::Arc{center:c2,..})=
        (a.curve,b.curve) else{return (vec![],true);};
    if dist(c1,c2)>0.0{
        // Near-coincident but not identical centers demand a separate,
        // numerically stable two-circle proof; never mistake for overlap.
        return (vec![],true);
    }
    let r1=dist(a.a,c1);
    let r2=dist(b.a,c2);
    if (r1-r2).abs()>r1.max(r2).max(1.0)*1e-7{
        return (vec![],false);
    }
    // Tiny concentric-radius disagreement is ambiguous at these CAD
    // tolerances. Reject rather than silently assuming a perfect circle.
    if (r1-r2).abs()>r1.max(r2).max(1.0)*1e-10{
        return (vec![],true);
    }
    let first=arc_angular_intervals(a);
    let second=arc_angular_intervals(b);
    for &(as_,ae) in &first{
        for &(bs,be) in &second{
            if ae.min(be)-as_.max(bs)>1e-9{
                return (vec![],true);
            }
        }
    }
    let mut hits=Vec::new();
    for p in [a.a,a.b,b.a,b.b]{
        if let (Some(t),Some(u))=(on_arc_parameter(a,p),on_arc_parameter(b,p)){
            if hits.iter().all(|(q,..)|dist(*q,p)>1e-7){
                hits.push((p,t,u));
            }
        }
    }
    (hits,false)
}

fn intersect(a:Edge,b:Edge)->(Vec<(Point,f64,f64)>,bool){
    match (a.curve,b.curve){
        (Curve::Line,Curve::Line)=>(line_line(a,b),false),
        (Curve::Line,Curve::Arc{..})=>(line_arc(a,b),false),
        (Curve::Arc{..},Curve::Line)=>{
            (line_arc(b,a).into_iter().map(|(p,u,t)|(p,t,u)).collect(),false)
        },
        (Curve::Arc{center:c1,..},Curve::Arc{center:c2,..})=>{
            if dist(c1,c2)<EPS{
                return coincident_arc_pair(a,b);
            }
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
/// Verify that one bounded analytic chain has no remote self-crossings,
/// unexpected tangencies, or overlapping source edges. This uses the same
/// retained line/circle solver as the intersection inspector, never preview
/// tessellation. Adjacent segments may meet only at their shared endpoint.
///
/// Coincident circles are compared by exact circular sweep intervals,
/// including seam wraparound. Adjacent single-endpoint joins are allowed;
/// overlapping angular intervals, unexpected remote contacts and
/// numerically ambiguous near-coincident supports still reject.
pub fn validate_simple_analytic_chain(path:&AnalyticPath)->Result<(),String>{
    path.validate()?;
    let count=path.segments.len();
    // AnalyticPath::validate bounds this to at most 256 segments (32640 pairs).
    let edges=(0..count).map(|i|Edge::in_world(path,i)).collect::<Vec<_>>();
    for i in 0..count {
        for j in i+1..count {
            let a=edges[i];
            let b=edges[j];
            let expected=if j==i+1 {
                Some(a.b)
            } else if path.closed && i==0 && j+1==count {
                Some(a.a)
            } else {
                None
            };
            let (hits,unresolved)=intersect(a,b);
            if unresolved {
                return Err(format!(
                    "Analytic contour edges {} and {} overlap or have unresolved coincident circles",
                    i+1,j+1
                ));
            }
            if hits.into_iter().any(|(p,..)|
                expected.is_none_or(|shared|dist(p,shared)>1e-7)) {
                return Err(format!(
                    "Analytic contour edges {} and {} cross/touch away from their shared endpoint",
                    i+1,j+1
                ));
            }
            // Parallel coincident LINES are reported as no isolated roots by
            // the general solver. Explicitly detect overlapping intervals and
            // nonadjacent end-to-end contact, including exact backtracking.
            if matches!(a.curve,Curve::Line) && matches!(b.curve,Curve::Line) {
                let u=sub(a.b,a.a);
                let v=sub(b.b,b.a);
                let length=norm(u);
                let other_length=norm(v);
                if length<1e-8 || other_length<1e-8 {
                    return Err("Degenerate straight contour edge".into());
                }
                if cross(u,v).abs()<=1e-12*length*other_length
                    && cross(u,sub(b.a,a.a)).abs()<=1e-7*length {
                    let t0=dot(sub(b.a,a.a),u)/(length*length);
                    let t1=dot(sub(b.b,a.a),u)/(length*length);
                    let lo=t0.min(t1).max(0.0);
                    let hi=t0.max(t1).min(1.0);
                    if hi>=lo-1e-7/length {
                        let contact=add(a.a,mul(u,(hi+lo)/2.0));
                        if (hi-lo)*length>1e-7 ||
                            expected.is_none_or(|shared|dist(contact,shared)>1e-7) {
                            return Err(format!(
                                "Analytic contour edges {} and {} overlap or touch unexpectedly",
                                i+1,j+1
                            ));
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

/// Extend a terminal straight-edge ray to the NEAREST source-accurate
/// crossing with another path. The reference stays unchanged. An overlap
/// (non-unique boundary) is a hard error, not an arbitrary guessed result.
pub fn nearest_extension_crossing(source:&AnalyticPath,target:&AnalyticPath,
    at_start:bool,max_distance_mm:f64)->Result<(Point,f64),String>{
    if source.id==target.id {
        return Err("Choose two different analytic vectors".into());
    }
    if source.closed{return Err("Extend to boundary requires an open source path".into());}
    if !max_distance_mm.is_finite() || !(0.001..=10000.0).contains(&max_distance_mm){
        return Err("Maximum extension must be 0.001–10000 mm".into());
    }
    let n=source.nodes.len();
    let edge=if at_start{0}else{source.segments.len()-1};
    if !matches!(source.segments[edge].curve,Curve::Line){
        return Err("Only an open straight terminal edge can extend to a boundary".into());
    }
    let index=if at_start{0}else{n-1};
    let inner=if at_start{1}else{n-2};
    let tip=source.nodes[index].position.offset(source.origin.x,source.origin.y);
    let previous=source.nodes[inner].position.offset(source.origin.x,source.origin.y);
    let outward=sub(tip,previous);
    let direction_len=norm(outward);
    if direction_len<1e-9{return Err("Source terminal edge has no direction".into());}
    let direction=mul(outward,1.0/direction_len);
    let ray=Edge{a:tip,b:add(tip,mul(direction,max_distance_mm)),
        curve:Curve::Line};
    let mut best:Option<(Point,f64)>=None;
    for j in 0..target.segments.len(){
        let reference=Edge::in_world(target,j);
        if matches!(reference.curve,Curve::Line){
            let dir=sub(reference.b,reference.a);
            let len=norm(dir);
            if len>1e-9
                && cross(direction,dir).abs()<=1e-10*len
                && cross(sub(reference.a,tip),direction).abs()<1e-7{
                let a=dot(sub(reference.a,tip),direction);
                let b=dot(sub(reference.b,tip),direction);
                if a.max(b)>0.001 && a.min(b)<max_distance_mm{
                    return Err("Reference overlaps the extension ray; boundary is ambiguous".into());
                }
            }
        }
        let (hits,unsupported)=intersect(ray,reference);
        if unsupported{
            return Err("Reference contains an overlapping or unresolved crossing; isolate simpler geometry".into());
        }
        for (p,t,_) in hits{
            let distance=t*max_distance_mm;
            if distance<0.001-1e-8 || distance>max_distance_mm+1e-7 {
                continue;
            }
            if best.is_none_or(|(_,earlier)|distance<earlier){
                best=Some((p,distance));
            }
        }
    }
    best.ok_or_else(||format!("No forward crossing within {max_distance_mm:.3} mm of the selected terminal end"))
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

    fn arc_edge(center:Point,r:f64,start_degrees:f64,
        end_degrees:f64,clockwise:bool)->Edge{
        let on_circle=|degrees:f64|{
            let angle=degrees.to_radians();
            add(center,Point::new(r*angle.cos(),r*angle.sin()))
        };
        Edge{a:on_circle(start_degrees),b:on_circle(end_degrees),
            curve:Curve::Arc{center,clockwise}}
    }
    fn chained_arcs(id:u64,degrees:&[f64],clockwise:&[bool],
        closed:bool)->AnalyticPath{
        let center=Point::new(20.0,30.0);
        let r=10.0;
        let nodes=degrees.iter().enumerate().map(|(i,angle)|{
            let t=angle.to_radians();
            crate::PathNode{id:i as u64+1,
                position:add(center,Point::new(r*t.cos(),r*t.sin()))}
        }).collect::<Vec<_>>();
        let segs=clockwise.iter().enumerate().map(|(i,clockwise)|{
            crate::PathSegment{id:100+i as u64,
                curve:Curve::Arc{center,clockwise:*clockwise}}
        }).collect::<Vec<_>>();
        let p=AnalyticPath{id,name:"Circle sweep".into(),
            origin:Point::new(5.0,7.0),visible:true,locked:false,closed,
            nodes,segments:segs,next_element_id:200};
        p.validate().unwrap();
        p
    }
    #[test]
    fn coincident_sweeps_allow_one_contact_across_zero_degree_seam(){
        let center=Point::new(10.0,10.0);
        let before=arc_edge(center,10.0,330.0,30.0,false);
        let after=arc_edge(center,10.0,30.0,100.0,false);
        let (hits,ambiguous)=intersect(before,after);
        assert!(!ambiguous);
        assert_eq!(hits.len(),1);
        assert!((hits[0].1-1.0).abs()<1e-9);
        assert!((hits[0].2).abs()<1e-9);
        assert!(dist(hits[0].0,before.b)<1e-7);
        let (swapped,ambiguous)=intersect(after,before);
        assert!(!ambiguous);
        assert_eq!(swapped.len(),1);
        assert!((swapped[0].1).abs()<1e-9);
        assert!((swapped[0].2-1.0).abs()<1e-9);
    }
    #[test]
    fn concentric_distinct_radii_do_not_create_unsupported_crossings(){
        let center=Point::new(0.0,0.0);
        let near=arc_edge(center,10.0,0.0,120.0,false);
        let far=arc_edge(center,20.0,0.0,120.0,false);
        let (hits,ambiguous)=intersect(near,far);
        assert!(hits.is_empty());
        assert!(!ambiguous);
        let mut project=Project::default();
        project.paths.extend([
            chained_arcs(1,&[0.0,120.0],&[false],false),
            chained_arcs(2,&[0.0,120.0],&[false],false)
        ]);
        let center=Point::new(20.0,30.0);
        for node in &mut project.paths[1].nodes{
            node.position=add(center,mul(sub(node.position,center),2.0));
        }
        project.next_id=3;
        project.validate().unwrap();
        let scan=find_intersections(&project,1).unwrap();
        assert_eq!(scan.unsupported_pairs,0);
    }
    #[test]
    fn circular_arc_overlap_and_backtrack_reject_even_across_seam(){
        let center=Point::new(0.0,0.0);
        let a=arc_edge(center,10.0,330.0,30.0,false);
        let b=arc_edge(center,10.0,30.0,345.0,true);
        assert!(intersect(a,b).1,"wraparound arcs overlap in angle");
        let backtrack=chained_arcs(1,&[0.0,90.0,0.0],
            &[false,true],false);
        assert!(validate_simple_analytic_chain(&backtrack)
            .unwrap_err().contains("overlap"));
        let repeated=chained_arcs(2,&[0.0,120.0,240.0],
            &[true,true,true],true);
        assert!(validate_simple_analytic_chain(&repeated).is_err(),
            "two circles worth of total sweep must not masquerade as one");
    }
    #[test]
    fn adjacent_and_remote_disjoint_same_circle_arcs_are_not_overlaps(){
        let simple=chained_arcs(1,&[0.0,90.0,180.0],&[false,false],false);
        validate_simple_analytic_chain(&simple).unwrap();
        let wrapped=chained_arcs(2,&[330.0,30.0,110.0],
            &[false,false],false);
        validate_simple_analytic_chain(&wrapped).unwrap();
        let full=chained_arcs(3,&[0.0,90.0,180.0,270.0],
            &[false,false,false,false],true);
        validate_simple_analytic_chain(&full).unwrap();
        let disjoint=crate::AnalyticPath{
            id:7,name:"Arc, chord, arc".into(),
            origin:Point::new(0.0,0.0),visible:true,locked:false,closed:false,
            nodes:vec![
                crate::PathNode{id:1,position:Point::new(10.0,0.0)},
                crate::PathNode{id:2,position:Point::new(0.0,10.0)},
                crate::PathNode{id:3,position:Point::new(-10.0,0.0)},
                crate::PathNode{id:4,position:Point::new(0.0,-10.0)},
            ],
            segments:vec![
                crate::PathSegment{id:5,curve:Curve::Arc{
                    center:Point::new(0.0,0.0),clockwise:false}},
                crate::PathSegment{id:6,curve:Curve::Line},
                crate::PathSegment{id:7,curve:Curve::Arc{
                    center:Point::new(0.0,0.0),clockwise:false}},
            ],next_element_id:8};
        disjoint.validate().unwrap();
        validate_simple_analytic_chain(&disjoint).unwrap();
    }
    #[test]
    fn nonadjacent_same_circle_endpoint_touch_is_rejected(){
        // The first and last edges are NOT neighbors in this open path,
        // so a remote shared circle point must remain an error.
        let p=crate::AnalyticPath{
            id:6,name:"Return".into(),origin:Point::new(0.0,0.0),
            visible:true,locked:false,closed:false,
            nodes:vec![
                crate::PathNode{id:1,position:Point::new(10.0,0.0)},
                crate::PathNode{id:2,position:Point::new(0.0,10.0)},
                crate::PathNode{id:3,position:Point::new(-10.0,0.0)},
                crate::PathNode{id:4,position:Point::new(10.0,0.0)},
            ],
            segments:vec![
                crate::PathSegment{id:5,curve:Curve::Arc{
                    center:Point::new(0.0,0.0),clockwise:false}},
                crate::PathSegment{id:6,curve:Curve::Line},
                crate::PathSegment{id:7,curve:Curve::Arc{
                    center:Point::new(0.0,0.0),clockwise:false}},
            ],next_element_id:8};
        p.validate().unwrap();
        assert!(validate_simple_analytic_chain(&p).is_err());
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
        let p=crate::shapes::polyline(1,"Five edges".into(),
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
    fn extends_ray_to_nearest_line_not_distant_crossing(){
        let horizontal=segment(1,Point::new(10.0,10.0),Point::new(20.0,10.0));
        let near=segment(2,Point::new(35.0,0.0),Point::new(35.0,25.0));
        let (target,distance)=nearest_extension_crossing(&horizontal,&near,false,20.0).unwrap();
        assert_eq!(target,Point::new(35.0,10.0));
        assert!((distance-15.0).abs()<1e-9);
        assert!(nearest_extension_crossing(&horizontal,&near,false,14.0).is_err());
        assert!(nearest_extension_crossing(&horizontal,&near,true,25.0).is_err());
        let west=segment(3,Point::new(2.0,0.0),Point::new(2.0,25.0));
        let (point,distance)=nearest_extension_crossing(&horizontal,&west,true,10.0).unwrap();
        assert_eq!(point,Point::new(2.0,10.0));
        assert!((distance-8.0).abs()<1e-9);
    }
    #[test]
    fn extend_ray_detects_true_cubic_boundary_and_distinct_origins(){
        let mut src=segment(1,Point::new(0.0,0.0),Point::new(10.0,0.0));
        src.origin=Point::new(10.0,25.0);
        let mut cubic=segment(2,Point::new(0.0,-10.0),Point::new(0.0,10.0));
        cubic.origin=Point::new(35.0,25.0);
        cubic.segments[0].curve=Curve::Cubic{
            control1:Point::new(0.0,-3.0),control2:Point::new(0.0,3.0)
        };
        let (hit,d)=nearest_extension_crossing(&src,&cubic,false,25.0).unwrap();
        assert!((hit.x-35.0).abs()<1e-7);
        assert!((hit.y-25.0).abs()<1e-7);
        assert!((d-15.0).abs()<1e-7);
    }
    #[test]
    fn extend_chooses_nearest_true_circular_arc_crossing(){
        let source=segment(1,Point::new(10.0,15.0),Point::new(20.0,15.0));
        let mut arc=segment(2,Point::new(30.0,10.0),Point::new(50.0,10.0));
        arc.segments[0].curve=Curve::Arc{
            center:Point::new(40.0,10.0),clockwise:true
        };
        let (hit,d)=nearest_extension_crossing(&source,&arc,false,40.0).unwrap();
        let nearest_x=40.0-(100.0_f64-25.0).sqrt();
        assert!((hit.x-nearest_x).abs()<1e-8);
        assert!((hit.y-15.0).abs()<1e-8);
        assert!((d-(nearest_x-20.0)).abs()<1e-8);
    }
    #[test]
    fn extension_collinear_overlap_fails_closed(){
        let src=segment(1,Point::new(10.0,0.0),Point::new(20.0,0.0));
        let overlap=segment(2,Point::new(25.0,0.0),Point::new(35.0,0.0));
        assert!(nearest_extension_crossing(&src,&overlap,false,20.0)
            .unwrap_err().contains("overlaps"));
        let behind=segment(3,Point::new(-15.0,0.0),Point::new(-5.0,0.0));
        assert!(nearest_extension_crossing(&src,&behind,false,20.0).is_err());
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
    #[test]
    fn whole_chain_guard_accepts_simple_open_and_closed_vectors(){
        let open=crate::shapes::polyline(1,"Open".into(),Point::new(4.0,7.0),
            vec![Point::new(0.0,0.0),Point::new(10.0,0.0),
                 Point::new(10.0,10.0)],false).unwrap();
        validate_simple_analytic_chain(&open).unwrap();
        let closed=crate::shapes::polyline(2,"Square".into(),Point::new(0.0,0.0),
            vec![Point::new(0.0,0.0),Point::new(20.0,0.0),
                 Point::new(20.0,20.0),Point::new(0.0,20.0)],true).unwrap();
        validate_simple_analytic_chain(&closed).unwrap();
    }
    #[test]
    fn whole_chain_guard_rejects_remote_crossings_and_nonadjacent_touches(){
        let cross=crate::shapes::polyline(1,"X".into(),Point::new(0.0,0.0),
            vec![Point::new(0.0,0.0),Point::new(10.0,10.0),
                 Point::new(0.0,10.0),Point::new(10.0,0.0)],false).unwrap();
        assert!(validate_simple_analytic_chain(&cross).unwrap_err().contains("cross/touch"));
        let touch=crate::shapes::polyline(2,"T".into(),Point::new(0.0,0.0),
            vec![Point::new(0.0,0.0),Point::new(10.0,0.0),
                 Point::new(10.0,10.0),Point::new(5.0,0.0)],false).unwrap();
        assert!(validate_simple_analytic_chain(&touch).is_err());
    }
    #[test]
    fn whole_chain_guard_rejects_collinear_backtrack(){
        let p=crate::shapes::polyline(1,"Backtrack".into(),Point::new(0.0,0.0),
            vec![Point::new(0.0,0.0),Point::new(10.0,0.0),
                 Point::new(5.0,0.0)],false).unwrap();
        assert!(validate_simple_analytic_chain(&p).unwrap_err().contains("overlap"));
    }

}
