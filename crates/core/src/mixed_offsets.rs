//! Exact parallel offsets of G1-tangent line/circular-arc chains.
//!
//! This is not a cubic Bézier approximation. Lines translate to exact
//! parallel lines and arcs retain their exact centers/sweeps with a
//! changed radius. Tangent line/arc/arc junctions meet at a common
//! analytic endpoint; straight/straight corners use bounded miters.
//! Sharp curved corners need a separate round/bevel-join solver and
//! deliberately fail rather than inventing a trimmed/extended arc.
use crate::{AnalyticPath,Curve,Point};
use std::f64::consts::TAU;

const EPS:f64=1e-9;
fn sub(a:Point,b:Point)->Point{Point::new(a.x-b.x,a.y-b.y)}
fn add(a:Point,b:Point)->Point{Point::new(a.x+b.x,a.y+b.y)}
fn mul(a:Point,k:f64)->Point{Point::new(a.x*k,a.y*k)}
fn dot(a:Point,b:Point)->f64{a.x*b.x+a.y*b.y}
fn cross(a:Point,b:Point)->f64{a.x*b.y-a.y*b.x}
fn len(a:Point)->f64{a.x.hypot(a.y)}
fn dist(a:Point,b:Point)->f64{len(sub(a,b))}
fn unit(a:Point)->Result<Point,String>{
    let n=len(a);
    if !n.is_finite()||n<EPS{return Err("Zero-length offset edge".into());}
    Ok(mul(a,1.0/n))
}
fn left(d:Point)->Point{Point::new(-d.y,d.x)}
#[derive(Clone,Copy)]
struct Shifted{start:Point,end:Point,curve:Curve}
/// Signed exact enclosed area from Green's theorem, not visual sampling.
fn exact_area(path:&AnalyticPath)->Result<f64,String>{
    if !path.closed{return Err("Winding requires a closed vector".into());}
    let mut twice=0.0;
    for (i,segment) in path.segments.iter().enumerate(){
        let a=path.nodes[i].position;
        let b=path.nodes[(i+1)%path.nodes.len()].position;
        match segment.curve{
            Curve::Line=>twice+=cross(a,b),
            Curve::Arc{center,clockwise}=>{
                let ra=sub(a,center);let rb=sub(b,center);
                let ra_len=len(ra);let rb_len=len(rb);
                if (ra_len-rb_len).abs()>1e-7*ra_len.max(1.0){
                    return Err("Inconsistent analytic circle radius".into());
                }
                let aa=ra.y.atan2(ra.x);
                let bb=rb.y.atan2(rb.x);
                let sweep=if clockwise{
                    -(aa-bb).rem_euclid(TAU)
                }else{
                    (bb-aa).rem_euclid(TAU)
                };
                if sweep.abs()<EPS{
                    return Err("Degenerate arc sweep in closed offset".into());
                }
                twice+=cross(center,sub(b,a))+ra_len*ra_len*sweep;
            }
            Curve::Cubic{..}=>{
                return Err("An exact cubic offset is not representable by a cubic Bézier in general".into());
            }
        }
    }
    let area=twice/2.0;
    if !area.is_finite()||area.abs()<EPS{
        return Err("Analytic closed path has degenerate signed area".into());
    }
    Ok(area)
}
fn displaced(path:&AnalyticPath,i:usize,left_amount:f64)
    ->Result<Shifted,String>{
    let a=path.nodes[i].position;
    let b=path.nodes[(i+1)%path.nodes.len()].position;
    let curve=path.segments[i].curve;
    match curve{
        Curve::Line=>{
            let tangent=unit(sub(b,a))?;
            let shift=mul(left(tangent),left_amount);
            Ok(Shifted{start:add(a,shift),end:add(b,shift),curve})
        }
        Curve::Arc{center,clockwise}=>{
            let radius=dist(a,center);
            let dr=if clockwise{left_amount}else{-left_amount};
            let adjusted=radius+dr;
            if adjusted<0.001||!adjusted.is_finite(){
                return Err("Offset collapses/reverses circular radius".into());
            }
            let factor=adjusted/radius;
            Ok(Shifted{
                start:add(center,mul(sub(a,center),factor)),
                end:add(center,mul(sub(b,center),factor)),
                curve,
            })
        }
        Curve::Cubic{..}=>Err("General cubic offset is not exact; no preview tessellation is used".into())
    }
}
fn join(prev:Shifted,next:Shifted,vertex:Point,offset:f64)
    ->Result<Point,String>{
    if matches!(prev.curve,Curve::Line)&&matches!(next.curve,Curve::Line){
        let a=sub(prev.end,prev.start);
        let b=sub(next.end,next.start);
        let den=cross(a,b);
        let norm=len(a)*len(b);
        if den.abs()<1e-12*norm{
            let ua=unit(a)?;let ub=unit(b)?;
            if dot(ua,ub)<0.999999 || dist(prev.end,next.start)>1e-6{
                return Err("Offset corner has reversing/parallel non-coincident straight edges".into());
            }
            return Ok(prev.end);
        }
        let t=cross(sub(next.start,prev.start),b)/den;
        let crossed=add(prev.start,mul(a,t));
        if dist(vertex,crossed)>offset.abs()*12.0+1e-7{
            return Err("Offset creates an excessively long line miter".into());
        }
        if !crossed.finite(){return Err("Nonfinite offset miter".into());}
        return Ok(crossed);
    }
    // Any junction containing an arc must have matching left normals:
    // this is exact at G1-tangent joints. A corner needs a separately
    // validated line/arc round join; do not create an approximate arc.
    let mismatch=dist(prev.end,next.start);
    if mismatch>1e-7*offset.abs().max(1.0){
        return Err(format!(
            "Line/arc junction is not tangent enough for an exact offset ({mismatch:.5} mm gap); round/trim join not available"
        ));
    }
    Ok(mul(add(prev.end,next.start),0.5))
}
/// Exact parallel offset for an open or closed chain with lines and true
/// circular arcs. Straight-only chains retain their older miter solver;
/// this function handles tangent line/arc seams and straight miters.
pub fn offset_tangent_chain(source:&AnalyticPath,mm:f64)
    ->Result<AnalyticPath,String>{
    if !mm.is_finite()||mm.abs()<0.001||mm.abs()>10000.0{
        return Err("Offset distance must be finite and 0.001–10000 mm".into());
    }
    if source.segments.iter().all(|s|matches!(s.curve,Curve::Line)){
        return Err("Straight-only contour should use the existing miter offset".into());
    }
    if source.segments.iter().any(|s|matches!(s.curve,Curve::Cubic{..})){
        return Err("Mixed/Cubic Bézier offsets are not exact cubic curves and remain unsupported".into());
    }
    // Refuse preexisting remote crossings: preserving every local tangent
    // alone cannot make a self-overlapping source into a safe offset.
    crate::intersections::validate_simple_analytic_chain(source)?;
    let amount=if source.closed{
        if exact_area(source)? > 0.0{-mm}else{mm}
    }else{mm};
    let edges=(0..source.segments.len())
        .map(|i|displaced(source,i,amount))
        .collect::<Result<Vec<_>,_>>()?;
    let n=source.nodes.len();
    let mut shifted=Vec::with_capacity(n);
    for i in 0..n{
        if !source.closed&&i==0{
            shifted.push(edges[0].start);continue;
        }
        if !source.closed&&i+1==n{
            shifted.push(edges[edges.len()-1].end);continue;
        }
        let prev=if i==0{edges.len()-1}else{i-1};
        shifted.push(join(edges[prev],edges[i],
            source.nodes[i].position,amount)?);
    }
    let mut result=source.clone();
    result.name=format!("{} exact offset {mm:.2} mm",source.name);
    for (node,p) in result.nodes.iter_mut().zip(shifted){
        node.position=p;
    }
    // A non-collapsing offset must preserve the winding of a valid
    // closed source. Area uses true signed circular sectors, not
    // a tessellated display/stock preview.
    if result.closed {
        let before=exact_area(source)?;
        let after=exact_area(&result)?;
        if before.signum()!=after.signum(){
            return Err("Closed offset reverses contour winding".into());
        }
    }
    result.validate()?;
    // A valid local offset may still intersect a distant edge. Check the
    // finished exact line/arc chain before the editor can commit it.
    crate::intersections::validate_simple_analytic_chain(&result)?;
    Ok(result)
}


/// A rounded offset is an explicit alternative to the legacy miter/tangent
/// solver. It connects only *convex on the requested offset side* corners
/// with a real circular arc centered at the original vertex, radius |mm|.
/// Inward sharp curved corners need a trimmed intersection, not a bridge.
#[derive(Clone,Copy)]
enum RoundedVertex {
    Common(Point),
    Arc { incoming:Point, outgoing:Point, center:Point, clockwise:bool },
}
fn edge_tangent(edge:Shifted,at_end:bool)->Result<Point,String>{
    let p=if at_end{edge.end}else{edge.start};
    match edge.curve{
        Curve::Line=>unit(sub(edge.end,edge.start)),
        Curve::Arc{center,clockwise}=>{
            let radial=unit(sub(p,center))?;
            Ok(if clockwise{mul(left(radial),-1.0)}else{left(radial)})
        }
        Curve::Cubic{..}=>Err("Cubic curves do not have exact circular parallel offsets".into())
    }
}

/// Parameters are measured along the displaced *finite* analytic edge,
/// never along an unbounded support or its preview polyline.
fn support_parameter(edge:Shifted,point:Point)->Option<f64>{
    let tol=1e-7*len(sub(edge.end,edge.start)).max(1.0);
    match edge.curve {
        Curve::Line=>{
            let delta=sub(edge.end,edge.start);
            let l2=dot(delta,delta);
            if l2<EPS*EPS{return None;}
            let t=dot(sub(point,edge.start),delta)/l2;
            if !(0.0..=1.0).contains(&t)
                || dist(add(edge.start,mul(delta,t)),point)>tol {return None;}
            Some(t)
        }
        Curve::Arc{center,clockwise}=>{
            let radius=dist(edge.start,center);
            if (dist(edge.end,center)-radius).abs()>tol
                || (dist(point,center)-radius).abs()>tol
                || radius<EPS{return None;}
            let begin=sub(edge.start,center);
            let finish=sub(edge.end,center);
            let query=sub(point,center);
            let a=begin.y.atan2(begin.x);
            let b=finish.y.atan2(finish.x);
            let q=query.y.atan2(query.x);
            let sweep=if clockwise{(a-b).rem_euclid(TAU)}
                      else{(b-a).rem_euclid(TAU)};
            if sweep<1e-9{return None;}
            let mut along=if clockwise{(a-q).rem_euclid(TAU)}
                          else{(q-a).rem_euclid(TAU)};
            if along>TAU-1e-9{along=0.0;}
            if along>sweep+1e-8{return None;}
            Some((along/sweep).clamp(0.0,1.0))
        }
        Curve::Cubic{..}=>None,
    }
}

/// Intersect infinite supporting lines/circles, then independently prove
/// that the candidate lies on both displaced finite edges. A joint is
/// admissible only if it trims the end of incoming and the start of
/// outgoing while leaving both portions strictly nonzero.
fn trim_concave_circular(prev:Shifted,next:Shifted,amount:f64)
    ->Result<Point,String>{
    let candidates=match (prev.curve,next.curve){
        (Curve::Line,Curve::Arc{center,..}) |
        (Curve::Arc{center,..},Curve::Line)=>{
            let (line,center,radius)=if matches!(prev.curve,Curve::Line){
                (prev,center,dist(next.start,center))
            } else {
                (next,center,dist(prev.start,center))
            };
            let direction=sub(line.end,line.start);
            let delta=sub(line.start,center);
            let aa=dot(direction,direction);
            if aa<EPS*EPS{return Err("Zero-length offset support line".into());}
            let bb=2.0*dot(delta,direction);
            let cc=dot(delta,delta)-radius*radius;
            let discr=bb*bb-4.0*aa*cc;
            let tolerance=(bb*bb+4.0*aa*cc.abs()).max(1.0)*1e-12;
            if discr< -tolerance{Vec::new()}else{
                let root=discr.max(0.0).sqrt();
                [(-bb-root)/(2.0*aa),(-bb+root)/(2.0*aa)]
                    .into_iter().map(|t|add(line.start,mul(direction,t)))
                    .collect::<Vec<_>>()
            }
        }
        (Curve::Arc{center:a,..},Curve::Arc{center:b,..})=>{
            let radius_a=dist(prev.start,a);
            let radius_b=dist(next.start,b);
            let separation=dist(a,b);
            if separation<EPS{
                return Err("Coincident circular supports need exact sweep-overlap proof".into());
            }
            if separation>radius_a+radius_b+1e-8 ||
                separation<(radius_a-radius_b).abs()-1e-8 {
                Vec::new()
            }else{
                let direction=mul(sub(b,a),1.0/separation);
                let advance=(radius_a*radius_a-radius_b*radius_b
                    +separation*separation)/(2.0*separation);
                let height2=radius_a*radius_a-advance*advance;
                if height2< -radius_a.max(1.0)*radius_a.max(1.0)*1e-10{
                    Vec::new()
                }else{
                    let mid=add(a,mul(direction,advance));
                    let orth=left(direction);
                    let h=height2.max(0.0).sqrt();
                    vec![add(mid,mul(orth,h)),sub(mid,mul(orth,h))]
                }
            }
        }
        _=>return Err("Concave circular trim needs a line/arc or arc/arc seam".into()),
    };
    let limit=amount.abs()*12.0+1e-7;
    let mut accepted=Vec::new();
    for hit in candidates{
        let (Some(incoming),Some(outgoing))=(
            support_parameter(prev,hit),support_parameter(next,hit))
        else{continue;};
        // Only REMOVE existing swept material. No extending a circle
        // outside the original arc and no reversing the traversal.
        if !(1e-7..1.0-1e-7).contains(&incoming)
            || !(1e-7..1.0-1e-7).contains(&outgoing)
            || dist(hit,prev.end)>limit || dist(hit,next.start)>limit{
            continue;
        }
        if accepted.iter().all(|p|dist(*p,hit)>1e-7){
            accepted.push(hit);
        }
    }
    match accepted.as_slice(){
        [only]=>Ok(*only),
        []=>Err("Concave circular supports do not meet on both original finite offset sweeps; no extrapolated trim".into()),
        _=>Err("Concave circular trim has multiple valid crossings; ambiguous join refused".into()),
    }
}
fn rounded_join(prev:Shifted,next:Shifted,vertex:Point,amount:f64)
    ->Result<RoundedVertex,String>{
    let incoming=edge_tangent(prev,true)?;
    let outgoing=edge_tangent(next,false)?;
    let turn=cross(incoming,outgoing).atan2(dot(incoming,outgoing));
    if (std::f64::consts::PI-turn.abs()).abs()<1e-6 {
        return Err("Reversing/U-turn corner has no safe round offset join".into());
    }
    if turn.abs()<1e-6 {
        return join(prev,next,vertex,amount).map(RoundedVertex::Common);
    }
    if turn*amount<0.0 {
        let radius=amount.abs();
        let from=sub(prev.end,vertex);
        let to=sub(next.start,vertex);
        let tol=1e-7*radius.max(1.0);
        if (len(from)-radius).abs()>tol || (len(to)-radius).abs()>tol {
            return Err("Round join tangency radius does not match the offset distance".into());
        }
        let start=from.y.atan2(from.x);
        let end=to.y.atan2(to.x);
        let sweep=if turn<0.0 {
            (start-end).rem_euclid(TAU)
        }else{
            (end-start).rem_euclid(TAU)
        };
        if sweep<=1e-6 || sweep>std::f64::consts::PI+1e-6
            || (sweep-turn.abs()).abs()>1e-6{
            return Err("Round join would create an invalid angular sweep".into());
        }
        return Ok(RoundedVertex::Arc{
            incoming:prev.end,outgoing:next.start,center:vertex,clockwise:turn<0.0,
        });
    }
    if matches!(prev.curve,Curve::Arc{..}) ||
        matches!(next.curve,Curve::Arc{..}) {
        return trim_concave_circular(prev,next,amount)
            .map(RoundedVertex::Common);
    }
    // The converging straight supports have an exact bounded miter.
    join(prev,next,vertex,amount).map(RoundedVertex::Common)
}

/// Source-faithful offset with true circular ROUND joins at convex corners.
/// Existing normal OffsetLines behavior is unchanged. Both source and result
/// must be globally simple; no display tessellation or CNC clearance claim.
/// Sharp concave circular joints, curve offsets and ambiguous overlaps reject.
pub fn offset_round_chain(source:&AnalyticPath,mm:f64)
    ->Result<AnalyticPath,String>{
    if !mm.is_finite() || !(0.001..=10000.0).contains(&mm.abs()) {
        return Err("Round offset requires a signed 0.001–10000 mm distance".into());
    }
    if source.segments.iter().any(|s|matches!(s.curve,Curve::Cubic{..})) {
        return Err("Cubic Bézier offsets are not exact circular/straight curves".into());
    }
    // Preserve the specialized entire-circle exact solver (including
    // compatible adjacent same-center arcs) before global mixed validation.
    if source.segments.iter().all(|s|matches!(s.curve,Curve::Arc{..})){
        match crate::topology::offset_circular(source,mm) {
            Ok(result)=>return Ok(result),
            Err(problem) if source.segments.len()==1=>return Err(problem),
            Err(_)=>{},
        }
    }
    crate::intersections::validate_simple_analytic_chain(source)?;
    let amount=if source.closed{
        if exact_area(source)?>0.0{-mm}else{mm}
    }else{mm};
    let edges=(0..source.segments.len())
        .map(|i|displaced(source,i,amount))
        .collect::<Result<Vec<_>,_>>()?;
    let n=source.nodes.len();
    let mut corners=Vec::with_capacity(n);
    for i in 0..n{
        if !source.closed && i==0 {
            corners.push(RoundedVertex::Common(edges[0].start));
        }else if !source.closed && i+1==n {
            corners.push(RoundedVertex::Common(edges[edges.len()-1].end));
        }else{
            let previous=if i==0{edges.len()-1}else{i-1};
            corners.push(rounded_join(edges[previous],edges[i],
                source.nodes[i].position,amount)?);
        }
    }
    let extra=corners.iter().filter(|c|matches!(c,RoundedVertex::Arc{..})).count();
    if n+extra>256 {
        return Err("Round offset exceeds 256 analytic nodes; reduce corner count".into());
    }
    let mut result=source.clone();
    result.name=format!("{} round offset {mm:.2} mm",source.name);
    result.nodes.clear();
    result.segments.clear();
    for (i,corner) in corners.into_iter().enumerate(){
        let original_id=source.nodes[i].id;
        match corner {
            RoundedVertex::Common(position)=>{
                result.nodes.push(crate::PathNode{id:original_id,position});
            }
            RoundedVertex::Arc{incoming,outgoing,center,clockwise}=>{
                let node_id=result.next_element_id;
                let segment_id=node_id.checked_add(1)
                    .ok_or("Round join element IDs exhausted")?;
                result.next_element_id=segment_id.checked_add(1)
                    .ok_or("Round join element IDs exhausted")?;
                result.nodes.push(crate::PathNode{id:original_id,position:incoming});
                result.nodes.push(crate::PathNode{id:node_id,position:outgoing});
                result.segments.push(crate::PathSegment{
                    id:segment_id,curve:Curve::Arc{center,clockwise},
                });
            }
        }
        if i<source.segments.len(){
            result.segments.push(source.segments[i].clone());
        }
    }
    result.validate()?;
    if result.closed && exact_area(source)?.signum()!=exact_area(&result)?.signum(){
        return Err("Round offset reverses the closed contour winding".into());
    }
    crate::intersections::validate_simple_analytic_chain(&result)?;
    Ok(result)
}

#[cfg(test)]
mod tests{
    use super::*;
    use crate::{PathNode,PathSegment,Primitive,topology::offset_exact};
    fn open_arc_then_line()->AnalyticPath{
        let mut p=AnalyticPath::preset(1,"Arc and line".into(),
            Point::new(5.0,7.0),Primitive::Arc,20.0,10.0).unwrap();
        p.nodes.push(PathNode{id:4,position:Point::new(20.0,-12.0)});
        p.segments.push(PathSegment{id:5,curve:Curve::Line});
        p.next_element_id=6;
        p.validate().unwrap();
        p
    }
    fn closed_racetrack()->AnalyticPath{
        let p=AnalyticPath{
            id:1,name:"Racetrack".into(),origin:Point::new(3.0,7.0),
            visible:true,locked:false,closed:true,
            nodes:vec![
                Point::new(0.0,0.0),Point::new(30.0,0.0),
                Point::new(30.0,20.0),Point::new(0.0,20.0),
            ].into_iter().enumerate().map(|(i,position)|PathNode{
                id:i as u64+1,position
            }).collect(),
            segments:vec![
                PathSegment{id:5,curve:Curve::Line},
                PathSegment{id:6,curve:Curve::Arc{
                    center:Point::new(30.0,10.0),clockwise:false,
                }},
                PathSegment{id:7,curve:Curve::Line},
                PathSegment{id:8,curve:Curve::Arc{
                    center:Point::new(0.0,10.0),clockwise:false,
                }},
            ],
            next_element_id:9,
        };
        p.validate().unwrap();p
    }
    #[test]
    fn exact_open_arc_line_offset_retains_radius_center_and_normal(){
        let source=open_arc_then_line();
        let result=offset_exact(&source,2.0).unwrap();
        assert_eq!(result.nodes[0].position,Point::new(-2.0,0.0));
        assert_eq!(result.nodes[1].position,Point::new(22.0,0.0));
        assert_eq!(result.nodes[2].position,Point::new(22.0,-12.0));
        assert_eq!(result.segments,source.segments);
        assert_eq!(result.origin,source.origin);
        assert_eq!(source.nodes[1].position,Point::new(20.0,0.0));
        result.validate().unwrap();
        let inward=offset_exact(&source,-2.0).unwrap();
        assert_eq!(inward.nodes[1].position,Point::new(18.0,0.0));
    }
    #[test]
    fn exact_closed_racetrack_outward_and_inward_preserve_arc_source(){
        let source=closed_racetrack();
        assert!(exact_area(&source).unwrap()>0.0);
        for (mm,expected_r) in [(3.0,13.0),(-2.0,8.0)]{
            let result=offset_exact(&source,mm).unwrap();
            assert!(result.closed);
            assert_eq!(result.segments,source.segments);
            assert_eq!(result.nodes[0].position,Point::new(0.0,-mm));
            assert_eq!(result.nodes[1].position,Point::new(30.0,-mm));
            let Curve::Arc{center,..}=result.segments[1].curve else{panic!("arc");};
            assert!((dist(result.nodes[1].position,center)-expected_r).abs()<1e-9);
            assert!(exact_area(&result).unwrap()>0.0);
            result.validate().unwrap();
        }
        assert!(offset_exact(&source,-10.0).is_err());
    }
    #[test]
    fn wrong_curved_corner_refuses_without_changing_source(){
        let mut source=open_arc_then_line();
        source.nodes[2].position=Point::new(32.0,0.0);
        source.validate().unwrap();
        let original=source.clone();
        assert!(offset_exact(&source,2.0).unwrap_err().contains("not tangent"));
        assert_eq!(original,source);
    }
    #[test]
    fn mixed_chain_supports_line_miter_before_true_tangent_arc(){
        let p=AnalyticPath{
            id:3,name:"Corner plus arc".into(),origin:Point::new(0.0,0.0),
            visible:true,locked:false,closed:false,
            nodes:vec![
                Point::new(0.0,0.0),Point::new(0.0,-10.0),
                Point::new(20.0,-10.0),Point::new(20.0,10.0),
            ].into_iter().enumerate().map(|(i,position)|PathNode{
                id:i as u64+1,position
            }).collect(),
            segments:vec![
                PathSegment{id:5,curve:Curve::Line},
                PathSegment{id:6,curve:Curve::Line},
                PathSegment{id:7,curve:Curve::Arc{
                    center:Point::new(20.0,0.0),clockwise:false
                }},
            ],
            next_element_id:8,
        };
        p.validate().unwrap();
        let shifted=offset_exact(&p,2.0).unwrap();
        assert!((shifted.nodes[1].position.x-2.0).abs()<1e-9);
        assert!((shifted.nodes[1].position.y+8.0).abs()<1e-9);
        assert!((shifted.nodes[2].position.y+8.0).abs()<1e-9);
        assert!(matches!(shifted.segments[2].curve,Curve::Arc{..}));
    }
    #[test]
    fn offset_refuses_remote_arc_line_self_intersection_without_editing_original(){
        let mut source=open_arc_then_line();
        source.nodes.push(PathNode{id:6,position:Point::new(0.0,12.0)});
        source.segments.push(PathSegment{id:7,curve:Curve::Line});
        source.next_element_id=8;
        source.validate().unwrap();
        let before=source.clone();
        let error=offset_exact(&source,2.0).unwrap_err();
        assert!(error.contains("cross/touch"),"Unexpected error: {error}");
        assert_eq!(source,before);
    }

    #[test]
    fn sharp_line_to_circle_gets_real_tangent_round_join_only_by_opt_in(){
        let mut p=AnalyticPath::preset(4,"Sharp".into(),
            Point::new(7.0,11.0),Primitive::Line,10.0,10.0).unwrap();
        p.nodes.push(PathNode{id:4,position:Point::new(20.0,-10.0)});
        p.segments.push(PathSegment{id:5,curve:Curve::Arc{
            center:Point::new(20.0,0.0),clockwise:false,
        }});
        p.next_element_id=6;
        p.validate().unwrap();
        assert!(offset_exact(&p,2.0).unwrap_err().contains("not tangent"));
        let before=p.clone();
        let rounded=offset_round_chain(&p,2.0).unwrap();
        assert_eq!(p,before);
        assert_eq!(rounded.nodes.len(),4);
        assert_eq!(rounded.segments.len(),3);
        assert_eq!(rounded.nodes[1].position,Point::new(10.0,2.0));
        assert_eq!(rounded.nodes[2].position,Point::new(12.0,0.0));
        assert_eq!(rounded.nodes[1].id,p.nodes[1].id);
        assert_eq!(rounded.segments[0].id,p.segments[0].id);
        assert_eq!(rounded.segments[2].id,p.segments[1].id);
        assert!(matches!(rounded.segments[1].curve,
            Curve::Arc{center,clockwise:true} if center==Point::new(10.0,0.0)));
        assert!(matches!(rounded.segments[2].curve,
            Curve::Arc{center,clockwise:false} if center==Point::new(20.0,0.0)));
        rounded.validate().unwrap();
        let trimmed=offset_round_chain(&p,-2.0).unwrap();
        let corner=trimmed.nodes[1].position;
        assert!((corner.x-(20.0-(144.0_f64-4.0).sqrt())).abs()<1e-7);
        assert!((corner.y+2.0).abs()<1e-7);
        assert_eq!(trimmed.nodes.len(),3);
        assert_eq!(trimmed.segments,p.segments);
        assert_eq!(trimmed.nodes[1].id,p.nodes[1].id);
        assert!((dist(corner,Point::new(20.0,0.0))-12.0).abs()<1e-7);
        crate::intersections::validate_simple_analytic_chain(&trimmed).unwrap();
    }
    #[test]
    fn sharp_arc_to_arc_round_join_keeps_both_original_circle_centers(){
        let p=AnalyticPath{
            id:2,name:"Double circle".into(),origin:Point::new(3.0,4.0),
            visible:true,locked:false,closed:false,
            nodes:vec![
                Point::new(-10.0,0.0),Point::new(0.0,-10.0),
                Point::new(10.0,-20.0)
            ].into_iter().enumerate().map(|(i,position)|PathNode{
                id:i as u64+1,position}).collect(),
            segments:vec![
                PathSegment{id:4,curve:Curve::Arc{
                    center:Point::new(0.0,0.0),clockwise:false}},
                PathSegment{id:5,curve:Curve::Arc{
                    center:Point::new(10.0,-10.0),clockwise:false}},
            ],next_element_id:6,
        };
        p.validate().unwrap();
        let result=offset_round_chain(&p,2.0).unwrap();
        assert_eq!(result.nodes.len(),4);
        assert_eq!(result.segments.len(),3);
        assert_eq!(result.origin,p.origin);
        assert!(matches!(result.segments[0].curve,Curve::Arc{
            center,clockwise:false} if center==Point::new(0.0,0.0)));
        assert!(matches!(result.segments[1].curve,Curve::Arc{
            center,clockwise:true} if center==Point::new(0.0,-10.0)));
        assert!(matches!(result.segments[2].curve,Curve::Arc{
            center,clockwise:false} if center==Point::new(10.0,-10.0)));
        crate::intersections::validate_simple_analytic_chain(&result).unwrap();
        let inward=offset_round_chain(&p,-2.0).unwrap();
        assert_eq!(inward.nodes.len(),3);
        assert_eq!(inward.segments,p.segments);
        let join=inward.nodes[1].position;
        assert!((dist(join,Point::new(0.0,0.0))-12.0).abs()<1e-7);
        assert!((dist(join,Point::new(10.0,-10.0))-12.0).abs()<1e-7);
        assert!(join.x<0.0 && join.y< -10.0);
        crate::intersections::validate_simple_analytic_chain(&inward).unwrap();
    }
    #[test]
    fn closed_ccw_triangle_rounds_outside_without_changing_winding(){
        let source=crate::shapes::polyline(5,"Triangle".into(),
            Point::new(0.0,0.0),vec![
                Point::new(0.0,0.0),Point::new(30.0,0.0),
                Point::new(15.0,25.0)
            ],true).unwrap();
        let result=offset_round_chain(&source,2.0).unwrap();
        assert_eq!(result.nodes.len(),6);
        assert_eq!(result.segments.len(),6);
        assert!(result.segments.iter().filter(|s|
            matches!(s.curve,Curve::Arc{..})).count()==3);
        assert!(exact_area(&result).unwrap()>exact_area(&source).unwrap());
        assert!(result.closed);
        crate::intersections::validate_simple_analytic_chain(&result).unwrap();
    }

    #[test]
    fn curved_to_straight_concave_trim_preserves_arc_center_and_ids(){
        let p=AnalyticPath{
            id:10,name:"Arc then line".into(),origin:Point::new(3.0,5.0),
            visible:true,locked:false,closed:false,
            nodes:vec![
                Point::new(20.0,-10.0),Point::new(10.0,0.0),
                Point::new(0.0,0.0)
            ].into_iter().enumerate().map(|(i,position)|PathNode{
                id:i as u64+1,position}).collect(),
            segments:vec![
                PathSegment{id:4,curve:Curve::Arc{
                    center:Point::new(20.0,0.0),clockwise:true}},
                PathSegment{id:5,curve:Curve::Line},
            ],next_element_id:6,
        };
        p.validate().unwrap();
        let original=p.clone();
        let result=offset_round_chain(&p,2.0).unwrap();
        assert_eq!(p,original);
        assert_eq!(result.segments,p.segments);
        assert_eq!(result.nodes.len(),3);
        let corner=result.nodes[1].position;
        assert!((corner.x-(20.0-(144.0_f64-4.0).sqrt())).abs()<1e-7);
        assert!((corner.y+2.0).abs()<1e-7);
        crate::intersections::validate_simple_analytic_chain(&result).unwrap();
    }

    #[test]
    fn invalid_trim_outside_original_short_circle_sweep_is_rejected(){
        let mut p=AnalyticPath::preset(11,"Short arc".into(),
            Point::new(0.0,0.0),Primitive::Line,10.0,10.0).unwrap();
        let angle=0.05_f64;
        p.nodes.push(PathNode{id:4,position:Point::new(
            20.0-10.0*angle.cos(),-10.0*angle.sin())});
        p.segments.push(PathSegment{id:5,curve:Curve::Arc{
            center:Point::new(20.0,0.0),clockwise:false,
        }});
        p.next_element_id=6;
        p.validate().unwrap();
        let before=p.clone();
        let err=offset_round_chain(&p,-2.0).unwrap_err();
        assert!(err.contains("finite offset sweeps"),"Unexpected: {err}");
        assert_eq!(p,before);
    }

    #[test]
    fn rounded_solver_rejects_reversals_cubics_and_nonfinite_offsets(){
        let p=crate::shapes::polyline(7,"Backtrack".into(),Point::new(0.0,0.0),
            vec![Point::new(0.0,0.0),Point::new(10.0,0.0),
                Point::new(5.0,0.0)],false).unwrap();
        assert!(offset_round_chain(&p,1.0).is_err());
        let cubic=AnalyticPath::preset(1,"Cubic".into(),
            Point::new(0.0,0.0),Primitive::Cubic,15.0,10.0).unwrap();
        assert!(offset_round_chain(&cubic,2.0).is_err());
        assert!(offset_round_chain(&cubic,f64::NAN).is_err());
    }

}
