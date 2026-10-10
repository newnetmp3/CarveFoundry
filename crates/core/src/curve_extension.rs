//! Source-preserving endpoint continuation. Exact circular arcs retain center
//! and radius; cubic Béziers continue their original polynomial outside [0,1]
//! and are reparameterized exactly to a new Bézier segment. Display preview
//! tessellation is never an input to the geometry or intersection solver.
use crate::{AnalyticPath,Curve,PathNode,PathSegment,Point};
use crate::{intersections,topology};
use std::f64::consts::TAU;

const EPS:f64=1e-8;
const MAX_CUBIC_PARAMETER_EXTENSION:f64=2.0;
fn add(a:Point,b:Point)->Point{Point::new(a.x+b.x,a.y+b.y)}
fn sub(a:Point,b:Point)->Point{Point::new(a.x-b.x,a.y-b.y)}
fn scale(a:Point,t:f64)->Point{Point::new(a.x*t,a.y*t)}
fn mix(a:Point,b:Point,t:f64)->Point{add(scale(a,1.0-t),scale(b,t))}
fn distance(a:Point,b:Point)->f64{(a.x-b.x).hypot(a.y-b.y)}
fn point_at(c:[Point;4],t:f64)->Point{
    let u=1.0-t;
    add(add(scale(c[0],u*u*u),scale(c[1],3.0*u*u*t)),
        add(scale(c[2],3.0*u*t*t),scale(c[3],t*t*t)))
}
fn velocity(c:[Point;4],t:f64)->Point{
    let u=1.0-t;
    add(add(scale(sub(c[1],c[0]),3.0*u*u),
        scale(sub(c[2],c[1]),6.0*u*t)),scale(sub(c[3],c[2]),3.0*t*t))
}
/// Algebraic reparameterization: same cubic polynomial on [a,b], even
/// beyond original parameters. No polyline approximation or extrapolated
/// independent "best-fit" controls.
fn interval(c:[Point;4],a:f64,b:f64)->[Point;4]{
    let dt=b-a;
    let start=point_at(c,a);let end=point_at(c,b);
    [start,add(start,scale(velocity(c,a),dt/3.0)),
        sub(end,scale(velocity(c,b),dt/3.0)),end]
}
fn prefix(c:[Point;4],t:f64)->[Point;4]{
    let ab=mix(c[0],c[1],t);let bc=mix(c[1],c[2],t);
    let cd=mix(c[2],c[3],t);
    let mid1=mix(ab,bc,t);let mid2=mix(bc,cd,t);
    [c[0],ab,mid1,mix(mid1,mid2,t)]
}
/// Arc length is only used as a reach LIMIT, never for deriving stored
/// CAD curve points. Fixed even Simpson quadrature with binary search over
/// parameter span and a conservative post-hit reach tolerance.
fn cubic_length(c:[Point;4],a:f64,b:f64)->f64{
    const N:usize=128;
    let h=(b-a)/(N as f64);
    let mut sum=0.0;
    for i in 0..=N{
        let t=a+h*i as f64;
        let d=velocity(c,t);
        let weight=if i==0||i==N{1.0}else if i%2==0{2.0}else{4.0};
        sum+=weight*d.x.hypot(d.y);
    }
    (sum*h/3.0).abs()
}
fn id(next:&mut u64)->Result<u64,String>{
    let n=*next;
    *next=n.checked_add(1).ok_or("Curve extension ran out of path element IDs")?;
    Ok(n)
}
fn candidate(source:&AnalyticPath,start:Point,end:Point,curve:Curve)->AnalyticPath{
    let mut p=source.clone();
    // A temporary exact one-segment path with the same source identity
    // so the ordinary crossing solver handles the stored coordinate frame.
    p.nodes=vec![
        PathNode{id:1,position:start},
        PathNode{id:2,position:end},
    ];
    p.segments=vec![PathSegment{id:3,curve}];
    p.closed=false;
    p.next_element_id=4;
    p
}
fn insert(path:&AnalyticPath,at_start:bool,new_tip:Point,curve:Curve)
    ->Result<AnalyticPath,String>{
    let mut p=path.clone();
    if p.nodes.len()>=256{return Err("Cannot extend: 256-node path limit".into());}
    let node=PathNode{id:id(&mut p.next_element_id)?,position:new_tip};
    let segment=PathSegment{id:id(&mut p.next_element_id)?,curve};
    if at_start{
        p.nodes.insert(0,node);
        p.segments.insert(0,segment);
    }else{
        p.nodes.push(node);
        p.segments.push(segment);
    }
    p.validate()?;
    Ok(p)
}
/// Continue an open endpoint to the nearest forward crossing with a separate
/// analytic reference path. Segment type remains line / circle / cubic.
/// Cubic continuation follows the original *polynomial*, preserving the
/// source's position, tangent and curvature at the seam (G2 geometric continuity).
/// Its parameter horizon is capped to avoid unlimited extrapolation.
pub fn extend_to_reference(source:&AnalyticPath,target:&AnalyticPath,
    at_start:bool,max_mm:f64)->Result<AnalyticPath,String>{
    if source.id==target.id{return Err("Choose distinct source/reference vectors".into());}
    if source.closed{return Err("Only open vectors have extendable endpoints".into());}
    if !max_mm.is_finite() || !(0.001..=10000.0).contains(&max_mm){
        return Err("Maximum extension distance must be 0.001–10,000 mm".into());
    }
    let index=if at_start{0}else{source.segments.len()-1};
    let seg=source.segments[index].curve;
    if matches!(seg,Curve::Line){
        let (_,mm)=intersections::nearest_extension_crossing(
            source,target,at_start,max_mm)?;
        return topology::extend_line(source,at_start,mm);
    }
    let tip=source.nodes[if at_start{0}else{source.nodes.len()-1}].position;
    let (probe,span_mm)=match seg{
        Curve::Arc{center,clockwise}=>{
            let r=distance(tip,center);
            if r<EPS{return Err("Circular source has no radius".into());}
            // One-turn cap avoids ambiguous coincident end positions.
            let radians=(max_mm/r).min(TAU-0.02);
            let signed=if clockwise!=at_start{-radians}else{radians};
            let theta=(tip.y-center.y).atan2(tip.x-center.x)+signed;
            let end=Point::new(center.x+r*theta.cos(),center.y+r*theta.sin());
            (candidate(source,tip,end,Curve::Arc{
                center,clockwise:clockwise!=at_start}),r*radians)
        }
        Curve::Cubic{control1,control2}=>{
            let a=if at_start{0.0}else{1.0};
            let p0=source.nodes[index].position;
            let p3=source.nodes[index+1].position;
            let c=[p0,control1,control2,p3];
            let sign=if at_start{-1.0}else{1.0};
            let tip_velocity=velocity(c,a);
            if tip_velocity.x.hypot(tip_velocity.y)<1e-8 {
                return Err("Cubic endpoint has zero derivative; a unique continuation direction is unavailable".into());
            }
            let bound=cubic_length(c,a,a+sign*MAX_CUBIC_PARAMETER_EXTENSION);
            if !bound.is_finite()||bound<EPS {
                return Err("Cubic continuation exceeds representable numeric bounds".into());
            }
            let span=if bound<=max_mm{MAX_CUBIC_PARAMETER_EXTENSION}else{
                let mut low=0.0;
                let mut high=MAX_CUBIC_PARAMETER_EXTENSION;
                for _ in 0..45{
                    let mid=0.5*(low+high);
                    if cubic_length(c,a,a+sign*mid)<=max_mm{
                        low=mid;
                    }else{high=mid;}
                }
                low
            };
            if span<1e-8{return Err("Requested cubic extension is too short".into());}
            let new_curve=interval(c,a,a+sign*span);
            if !new_curve.iter().all(|p|p.finite()){
                return Err("Cubic extrapolation exceeded coordinate limits".into());
            }
            (candidate(source,new_curve[0],new_curve[3],
                Curve::Cubic{control1:new_curve[1],control2:new_curve[2]}),
                cubic_length(c,a,a+sign*span))
        }
        Curve::Line=>unreachable!(),
    };
    probe.validate()?;
    let mut best:Option<(Point,f64,f64)>=None;
    for seg_id in target.segments.iter().map(|s|s.id){
        let (hits,unsupported)=intersections::segment_crossings(
            &probe,3,target,seg_id)?;
        if unsupported{
            return Err("Reference overlaps or has an unresolved curve crossing; simplify/select a different reference".into());
        }
        for hit in hits{
            let traveled=match probe.segments[0].curve{
                Curve::Arc{..}=>span_mm*hit.source_t,
                Curve::Cubic{control1,control2}=>{
                    let c=[probe.nodes[0].position,control1,control2,
                        probe.nodes[1].position];
                    cubic_length(c,0.0,hit.source_t)
                }
                Curve::Line=>unreachable!()
            };
            if !traveled.is_finite()||traveled<0.001||traveled>max_mm+1e-5{
                continue;
            }
            if best.is_none_or(|(_,_,old)|traveled<old){
                best=Some((hit.position,hit.source_t,traveled));
            }
        }
    }
    let (_,fraction,_)=best.ok_or_else(||format!(
        "No forward source-curve intersection within {max_mm:.3} mm; try another endpoint/reference (cubics are limited to two additional parameter lengths)"))?;
    let reference_curve=probe.segments[0].curve;
    let local_tip=match reference_curve{
        Curve::Arc{center,..}=>{
            let t=fraction;
            let start=probe.nodes[0].position;
            let end=probe.nodes[1].position;
            let a=(start.y-center.y).atan2(start.x-center.x);
            let b=(end.y-center.y).atan2(end.x-center.x);
            let sweep=if let Curve::Arc{clockwise:true,..}=reference_curve{
                -(a-b).rem_euclid(TAU)
            }else{(b-a).rem_euclid(TAU)};
            let theta=a+sweep*t;
            let r=distance(start,center);
            Point::new(center.x+r*theta.cos(),center.y+r*theta.sin())
        }
        Curve::Cubic{control1,control2}=>{
            let c=[probe.nodes[0].position,control1,control2,
                probe.nodes[1].position];
            prefix(c,fraction)[3]
        }
        Curve::Line=>unreachable!()
    };
    let new_curve=match reference_curve{
        Curve::Arc{center,clockwise}=>{
            Curve::Arc{center,clockwise:if at_start{!clockwise}else{clockwise}}
        }
        Curve::Cubic{control1,control2}=>{
            let full=[tip,control1,control2,probe.nodes[1].position];
            let section=prefix(full,fraction);
            if at_start{
                Curve::Cubic{control1:section[2],control2:section[1]}
            }else{
                Curve::Cubic{control1:section[1],control2:section[2]}
            }
        }
        Curve::Line=>unreachable!()
    };
    insert(source,at_start,local_tip,new_curve)
}

#[cfg(test)]
mod tests{
    use super::*;
    use crate::{Primitive,shapes::polyline};
    fn cross(a:Point,b:Point)->f64{a.x*b.y-a.y*b.x}
    fn line(id:u64,a:Point,b:Point)->AnalyticPath{
        polyline(id,"Reference".into(),Point::new(0.0,0.0),vec![a,b],false)
            .unwrap()
    }
    #[test]
    fn cubic_forward_continuation_reaches_boundary_without_flattening(){
        let original=AnalyticPath::preset(1,"Cubic".into(),Point::new(10.0,20.0),
            Primitive::Cubic,20.0,10.0).unwrap();
        let boundary=line(2,Point::new(31.0,-20.0),Point::new(31.0,70.0));
        let extended=extend_to_reference(&original,&boundary,false,60.0).unwrap();
        assert_eq!(extended.nodes.len(),3);
        assert_eq!(extended.segments.len(),2);
        assert_eq!(extended.segments[0],original.segments[0]);
        assert_eq!(original.nodes[1],extended.nodes[1]);
        assert!((extended.nodes[2].position.x+original.origin.x-31.0).abs()<1e-6);
        assert!(matches!(extended.segments[1].curve,Curve::Cubic{..}));
        let Curve::Cubic{control1,control2} = original.segments[0].curve
            else{panic!("expected cubic");};
        let old=[original.nodes[0].position,control1,control2,original.nodes[1].position];
        let Curve::Cubic{control1:new1,..}=extended.segments[1].curve
            else{panic!("expected continued cubic");};
        let previous_tangent=sub(old[3],old[2]);
        let extension_tangent=sub(new1,old[3]);
        assert!(cross(previous_tangent,extension_tangent).abs()<1e-7);
        assert!(previous_tangent.x*extension_tangent.x
            +previous_tangent.y*extension_tangent.y>0.0);
        extended.validate().unwrap();
    }
    #[test]
    fn reversed_cubic_start_continues_polynomial_in_backward_direction(){
        let source=AnalyticPath::preset(1,"Curve".into(),Point::new(0.0,0.0),
            Primitive::Cubic,20.0,12.0).unwrap();
        let boundary=line(2,Point::new(-2.0,-50.0),Point::new(-2.0,50.0));
        let extended=extend_to_reference(&source,&boundary,true,100.0).unwrap();
        assert_eq!(extended.nodes.len(),3);
        assert!(extended.nodes[0].position.x<0.0);
        assert_eq!(extended.nodes[1],source.nodes[0]);
        assert_eq!(extended.segments[1],source.segments[0]);
        extended.validate().unwrap();
    }
    #[test]
    fn true_circular_arc_continues_same_circle_and_winding(){
        let arc=AnalyticPath::preset(1,"Arc".into(),Point::new(0.0,0.0),
            Primitive::Arc,20.0,10.0).unwrap();
        let reference=line(2,Point::new(25.0,-40.0),Point::new(25.0,40.0));
        // This reference is beyond the radius and therefore cannot
        // intersect the continued circle. Refuse instead of flattening.
        assert!(extend_to_reference(&arc,&reference,false,60.0).is_err());
        let reference=line(3,Point::new(17.0,-50.0),Point::new(17.0,50.0));
        let grown=extend_to_reference(&arc,&reference,false,60.0).unwrap();
        assert!(matches!(grown.segments[1].curve,Curve::Arc{..}));
        let Curve::Arc{center,..}=grown.segments[1].curve else{panic!("arc");};
        assert!((distance(grown.nodes[2].position,center)-10.0).abs()<1e-7);
        grown.validate().unwrap();
    }
    #[test]
    fn curve_extension_rejects_zero_reach_and_wrong_sources(){
        let p=AnalyticPath::preset(1,"Curve".into(),Point::new(0.0,0.0),
            Primitive::Cubic,20.0,10.0).unwrap();
        let target=line(2,Point::new(100.0,0.0),Point::new(100.0,40.0));
        let before=p.clone();
        assert!(extend_to_reference(&p,&target,false,0.0).is_err());
        assert!(extend_to_reference(&p,&target,false,1.0).is_err());
        assert!(extend_to_reference(&p,&p,false,100.0).is_err());
        assert_eq!(before,p);
    }
}
