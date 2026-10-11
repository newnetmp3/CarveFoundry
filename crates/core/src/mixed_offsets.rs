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
    let amount=if source.closed{
        if exact_area(source)?>0.0{-mm}else{mm}
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
}
