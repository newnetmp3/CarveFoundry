//! Exact, bounded topology edits on retained source geometry, NEVER preview samples.
//! All functions return a validated draft; Editor commits one atomic Undo step.
use crate::{AnalyticPath,Curve,PathNode,PathSegment,Point};
use crate::geometry::{signed_area,validate_polygon};
use std::f64::consts::TAU;

const EPS:f64=1e-8;
fn add(a:Point,b:Point)->Point{Point::new(a.x+b.x,a.y+b.y)}
fn sub(a:Point,b:Point)->Point{Point::new(a.x-b.x,a.y-b.y)}
fn scale(a:Point,k:f64)->Point{Point::new(a.x*k,a.y*k)}
fn mix(a:Point,b:Point,t:f64)->Point{add(scale(a,1.0-t),scale(b,t))}
fn cross(a:Point,b:Point)->f64{a.x*b.y-a.y*b.x}
fn norm(v:Point)->f64{v.x.hypot(v.y)}
fn dist(a:Point,b:Point)->f64{norm(sub(a,b))}
fn unit(v:Point)->Result<Point,String>{
    let length=norm(v);
    if length<EPS || !length.is_finite(){return Err("Degenerate vector edge".into());}
    Ok(scale(v,1.0/length))
}
fn left(a:Point)->Point{Point::new(-a.y,a.x)}
fn id(next:&mut u64)->Result<u64,String>{
    let old=*next;*next=old.checked_add(1).ok_or("Path element IDs exhausted")?;
    Ok(old)
}
fn point(path:&AnalyticPath,i:usize)->Point{path.nodes[i].position}
fn next_point(path:&AnalyticPath,i:usize)->Point{point(path,(i+1)%path.nodes.len())}
fn split(a:Point,b:Point,curve:Curve,t:f64)->Result<(Point,Curve,Curve),String>{
    if !(0.0001..=0.9999).contains(&t){
        return Err("Split fraction must be between 0.0001 and 0.9999".into());
    }
    match curve{
        Curve::Line=>{
            Ok((mix(a,b,t),Curve::Line,Curve::Line))
        }
        Curve::Cubic{control1:c,control2:d}=>{
            // de Casteljau subdivision exactly preserves original cubic locus.
            let ac=mix(a,c,t);let cd=mix(c,d,t);let db=mix(d,b,t);
            let e=mix(ac,cd,t);let f=mix(cd,db,t);
            let m=mix(e,f,t);
            Ok((m,Curve::Cubic{control1:ac,control2:e},
                Curve::Cubic{control1:f,control2:db}))
        }
        Curve::Arc{center,clockwise}=>{
            let r=dist(a,center);
            let start=(a.y-center.y).atan2(a.x-center.x);
            let end=(b.y-center.y).atan2(b.x-center.x);
            let angle=if clockwise{-(start-end).rem_euclid(TAU)}
                else{(end-start).rem_euclid(TAU)};
            if angle.abs()<EPS||!r.is_finite(){return Err("Arc sweep is degenerate".into());}
            let mid=start+angle*t;
            Ok((Point::new(center.x+r*mid.cos(),center.y+r*mid.sin()),
                Curve::Arc{center,clockwise},Curve::Arc{center,clockwise}))
        }
    }
}
/// Insert a point on any analytic edge: line, true circle arc, or cubic.
/// The original segment identity remains on the first half.
pub fn split_segment(path:&AnalyticPath,segment_id:u64,t:f64)
    ->Result<(AnalyticPath,u64),String>{
    let mut p=path.clone();
    let i=p.segments.iter().position(|s|s.id==segment_id)
        .ok_or("Unknown segment for split")?;
    if p.nodes.len()>=256{return Err("Path has the maximum 256 nodes".into());}
    let (m,l,r)=split(point(&p,i),next_point(&p,i),p.segments[i].curve,t)?;
    let new_node=id(&mut p.next_element_id)?;
    let new_segment=id(&mut p.next_element_id)?;
    p.nodes.insert(i+1,PathNode{id:new_node,position:m});
    p.segments[i].curve=l;
    p.segments.insert(i+1,PathSegment{id:new_segment,curve:r});
    p.validate()?;
    Ok((p,new_node))
}
/// Trims the FIRST or LAST segment of an OPEN path to a fraction.
/// No preview approximation, no deletion of unrelated path nodes.
pub fn trim_endpoint(path:&AnalyticPath,at_start:bool,t:f64)->Result<AnalyticPath,String>{
    if path.closed{return Err("Trim endpoints requires an open vector".into());}
    let mut p=path.clone();
    let i=if at_start{0}else{p.segments.len()-1};
    let (middle,l,r)=split(point(&p,i),next_point(&p,i),p.segments[i].curve,t)?;
    if at_start{
        p.nodes[0].position=middle;
        p.segments[0].curve=r;
    }else{
        p.nodes[i+1].position=middle;
        p.segments[i].curve=l;
    }
    p.validate()?;
    Ok(p)
}
/// Extend an open vector by the specified distance, for straight terminal
/// segments only. No unverified tangent extrapolation of arcs/cubics.
pub fn extend_line(path:&AnalyticPath,at_start:bool,mm:f64)->Result<AnalyticPath,String>{
    if path.closed{return Err("Extend requires an open vector".into());}
    if !mm.is_finite() || !(0.001..=10000.0).contains(&mm){
        return Err("Extension must be between 0.001 and 10000 mm".into());
    }
    let mut p=path.clone();
    let i=if at_start{0}else{p.segments.len()-1};
    if !matches!(p.segments[i].curve,Curve::Line){
        return Err("Extend only supports straight terminal segments".into());
    }
    let direction=if at_start{sub(point(&p,0),point(&p,1))}
        else{sub(point(&p,i+1),point(&p,i))};
    let delta=scale(unit(direction)?,mm);
    let node=if at_start{0}else{p.nodes.len()-1};
    p.nodes[node].position=add(p.nodes[node].position,delta);
    p.validate()?;
    Ok(p)
}
fn reversed(mut path:AnalyticPath)->AnalyticPath{
    // Reordering retains each node ID; reverse controls/sweep analytically.
    path.nodes.reverse();
    path.segments.reverse();
    for segment in &mut path.segments{
        segment.curve=match segment.curve{
            Curve::Line=>Curve::Line,
            Curve::Arc{center,clockwise}=>Curve::Arc{center,clockwise:!clockwise},
            Curve::Cubic{control1,control2}=>Curve::Cubic{
                control1:control2,control2:control1,
            }
        };
    }
    path
}
/// Join two open paths at their NEAREST endpoints (any winding).
/// Exact touching endpoints share one node; short gaps <= tolerance use a
/// real retained LINE bridge rather than distorting a true arc/cubic.
pub fn join_open(a:&AnalyticPath,b:&AnalyticPath,tolerance:f64)
    ->Result<AnalyticPath,String>{
    if a.closed||b.closed {return Err("Join requires two open paths".into());}
    if !tolerance.is_finite() || !(0.0..=5.0).contains(&tolerance){
        return Err("Join gap tolerance must be 0–5 mm".into());
    }
    let ea=[a.nodes[0].position,a.nodes.last().ok_or("A has no endpoint")?.position];
    let eb=[b.nodes[0].position,b.nodes.last().ok_or("B has no endpoint")?.position];
    let aw=|p:Point|p.offset(a.origin.x,a.origin.y);
    let bw=|p:Point|p.offset(b.origin.x,b.origin.y);
    let mut candidates=[
        (dist(aw(ea[1]),bw(eb[0])),false,false),
        (dist(aw(ea[0]),bw(eb[0])),true,false),
        (dist(aw(ea[1]),bw(eb[1])),false,true),
        (dist(aw(ea[0]),bw(eb[1])),true,true),
    ];
    candidates.sort_by(|x,y|x.0.total_cmp(&y.0));
    let (gap,reverse_a,reverse_b)=candidates[0];
    if gap>tolerance+EPS{
        return Err(format!("Closest endpoints are {gap:.4} mm apart; increase join tolerance"));
    }
    let mut output=if reverse_a{reversed(a.clone())}else{a.clone()};
    let mut other=if reverse_b{reversed(b.clone())}else{b.clone()};
    let translation=sub(b.origin,a.origin);
    for node in &mut other.nodes{node.position=add(node.position,translation);}
    for seg in &mut other.segments{
        seg.curve=match seg.curve{
            Curve::Line=>Curve::Line,
            Curve::Arc{center,clockwise}=>Curve::Arc{
                center:add(center,translation),clockwise,
            },
            Curve::Cubic{control1,control2}=>Curve::Cubic{
                control1:add(control1,translation),control2:add(control2,translation),
            },
        };
    }
    let touching=gap<=EPS;
    if !touching {
        let bridge=id(&mut output.next_element_id)?;
        output.segments.push(PathSegment{id:bridge,curve:Curve::Line});
    }
    for (i,node) in other.nodes.iter().enumerate(){
        if touching && i==0{continue;}
        output.nodes.push(PathNode{
            id:id(&mut output.next_element_id)?,
            position:node.position,
        });
    }
    for segment in other.segments{
        output.segments.push(PathSegment{
            id:id(&mut output.next_element_id)?,
            curve:segment.curve,
        });
    }
    output.validate()?;
    Ok(output)
}
fn intersection(a:Point,da:Point,b:Point,db:Point)->Result<Point,String>{
    let den=cross(da,db);
    if den.abs()<1e-10{
        let ua=unit(da)?;let ub=unit(db)?;
        if ua.x*ub.x+ua.y*ub.y < 0.999999{
            return Err("Offset has opposing/near-parallel corner edges".into());
        }
        // Parallel consecutive edges: use the shared offset line.
        return Ok(b);
    }
    let t=cross(sub(b,a),db)/den;
    Ok(add(a,scale(da,t)))
}
/// Analytic parallel offset on straight paths only; no curve flattening.
/// Positive = left side for OPEN paths, OUTWARD for CLOSED paths.
pub fn offset_lines(source:&AnalyticPath,mm:f64)->Result<AnalyticPath,String>{
    if !mm.is_finite() || mm.abs()<0.001 || mm.abs()>10000.0{
        return Err("Offset distance must be between 0.001 and 10000 mm".into());
    }
    if source.segments.iter().any(|s|!matches!(s.curve,Curve::Line)){
        return Err("Exact offset currently requires all-straight vector edges; arc/cubic offset is not approximated".into());
    }
    let n=source.nodes.len();
    let points=source.nodes.iter().map(|v|v.position).collect::<Vec<_>>();
    let amount=if source.closed {
        let area=signed_area(&points);
        if area.abs()<EPS{return Err("Degenerate closed contour".into());}
        if area>0.0{-mm}else{mm}
    }else{mm};
    let edges=source.segments.len();
    let mut dirs=Vec::with_capacity(edges);
    let mut normals=Vec::with_capacity(edges);
    for i in 0..edges{
        let direction=sub(points[(i+1)%n],points[i]);
        let d=unit(direction)?;
        dirs.push(direction);
        normals.push(scale(left(d),amount));
    }
    let mut shifted=Vec::with_capacity(n);
    for i in 0..n{
        if !source.closed && i==0{
            shifted.push(add(points[0],normals[0]));continue;
        }
        if !source.closed && i==n-1{
            shifted.push(add(points[i],normals[edges-1]));continue;
        }
        let before=if i==0{edges-1}else{i-1};
        let prev=add(points[i],normals[before]);
        let next=add(points[i],normals[i]);
        let vertex=intersection(prev,dirs[before],next,dirs[i])?;
        if dist(vertex,points[i])>mm.abs()*12.0+EPS{
            return Err("Offset corner requires an unsafe miter; reduce distance".into());
        }
        shifted.push(vertex);
    }
    if shifted.iter().any(|p|!p.offset(source.origin.x,source.origin.y).finite()){
        return Err("Offset exceeds bounded stock coordinates".into());
    }
    if source.closed{
        validate_polygon(&shifted)
            .map_err(|_|"Offset contour self-intersects or collapses; adjust distance")?;
    }
    let mut output=source.clone();
    output.name=format!("{} offset {mm:.2} mm",source.name);
    output.nodes.iter_mut().zip(shifted).for_each(|(node,p)|node.position=p);
    output.validate()?;
    Ok(output)
}
/// Source-exact parallel offset of one OPEN circular arc, or a CLOSED
/// concentric all-arc circle. Does not approximate arbitrary curved offsets.
/// Open arcs: + means left of travel; closed circles: + means outward.
pub fn offset_circular(source:&AnalyticPath,mm:f64)->Result<AnalyticPath,String>{
    if !mm.is_finite() || mm.abs()<0.001 || mm.abs()>10000.0 {
        return Err("Circular offset must be 0.001–10000 mm (signed)".into());
    }
    if !source.closed && source.segments.len()!=1{
        return Err("Circular offsets require one open arc or a complete concentric circle".into());
    }
    let Curve::Arc{center,clockwise}=source.segments[0].curve else {
        return Err("A true circular arc is required for exact circular offset".into());
    };
    if source.segments.iter().any(|s|s.curve!=(Curve::Arc{center,clockwise})){
        return Err("Circle offset requires one common center and sweep direction".into());
    }
    let radius=dist(point(source,0),center);
    if source.nodes.iter().any(|n|(dist(n.position,center)-radius).abs()>1e-7*radius.max(1.0)){
        return Err("Circular arc radii are inconsistent".into());
    }
    let new_radius=radius+if source.closed{mm}else if clockwise{mm}else{-mm};
    if new_radius<0.001 {
        return Err("Offset radius collapses or reverses direction".into());
    }
    let ratio=new_radius/radius;
    let mut draft=source.clone();
    for node in &mut draft.nodes{
        node.position=add(center,scale(sub(node.position,center),ratio));
    }
    draft.name=format!("{} arc offset {mm:.2} mm",source.name);
    draft.validate()?;
    Ok(draft)
}
/// Dispatch to a mathematically representable exact parallel.
/// Cubics, multi-center arc chains and mixed edges fail closed.
pub fn offset_exact(source:&AnalyticPath,mm:f64)->Result<AnalyticPath,String>{
    if source.segments.iter().all(|s|matches!(s.curve,Curve::Line)){
        offset_lines(source,mm)
    }else if source.segments.iter().all(|s|matches!(s.curve,Curve::Arc{..})){
        offset_circular(source,mm)
    }else{
        Err("Exact mixed-curve/cubic offset unavailable; source remains unchanged".into())
    }
}
/// Exact chamfer/fillet of a selected line-line corner (interior for open,
/// any corner for closed). Adjacent straight source edges are preserved,
/// and a fillet is an exact circular arc with a tangent radius.
pub fn corner(path:&AnalyticPath,node_id:u64,distance_mm:f64,radius:bool)
    ->Result<AnalyticPath,String>{
    if !distance_mm.is_finite() || !(0.001..=10000.0).contains(&distance_mm){
        return Err("Corner size must be 0.001–10000 mm".into());
    }
    let mut out=path.clone();
    let i=out.nodes.iter().position(|n|n.id==node_id)
        .ok_or("Corner node not found")?;
    if !out.closed && (i==0||i+1>=out.nodes.len()){
        return Err("Open path corners must be interior nodes".into());
    }
    let incoming_edge=if i==0{out.segments.len()-1}else{i-1};
    if !matches!(out.segments[incoming_edge].curve,Curve::Line) ||
        !matches!(out.segments[i].curve,Curve::Line){
        return Err("Corner editing currently supports line-line junctions only".into());
    }
    if out.nodes.len()>=256{return Err("Maximum editable node count reached".into());}
    let prev=point(&out,if i==0{out.nodes.len()-1}else{i-1});
    let mid=point(&out,i);
    let next=point(&out,(i+1)%out.nodes.len());
    let incoming=unit(sub(mid,prev))?;let outgoing=unit(sub(next,mid))?;
    let turn=cross(incoming,outgoing);
    if turn.abs()<1e-8{return Err("A fillet/chamfer needs a non-collinear corner".into());}
    let dot=incoming.x*outgoing.x+incoming.y*outgoing.y;
    let tangent=if radius{
        // Tangent distance = radius * tan(turn_angle / 2).
        distance_mm*turn.abs()/(1.0+dot)
    }else{distance_mm};
    if !tangent.is_finite()||tangent>=dist(prev,mid)-EPS||
        tangent>=dist(mid,next)-EPS{
        return Err("Corner radius/bevel exceeds available straight edges".into());
    }
    let enter=sub(mid,scale(incoming,tangent));
    let exit=add(mid,scale(outgoing,tangent));
    let curve=if radius{
        let sign=turn.signum();
        let center=add(enter,scale(left(incoming),distance_mm*sign));
        if (dist(exit,center)-distance_mm).abs()>1e-6{
            return Err("Computed fillet is not tangent to both lines".into());
        }
        Curve::Arc{center,clockwise:sign<0.0}
    }else{Curve::Line};
    out.nodes[i].position=enter;
    let new_node=id(&mut out.next_element_id)?;
    let new_segment=id(&mut out.next_element_id)?;
    out.nodes.insert(i+1,PathNode{id:new_node,position:exit});
    out.segments.insert(i,PathSegment{id:new_segment,curve});
    out.validate()?;
    Ok(out)
}

#[cfg(test)]
mod tests{
    use super::*;
    use crate::{Primitive,ShapeKind,create_shape};
    fn demo(kind:Primitive)->AnalyticPath{
        AnalyticPath::preset(2,"Demo".into(),Point::new(12.0,15.0),
            kind,40.0,20.0).unwrap()
    }
    fn point_on(curve:&AnalyticPath,i:usize,t:f64)->Point{
        let a=curve.nodes[i].position;let b=curve.nodes[(i+1)%curve.nodes.len()].position;
        if t<=0.0{return a;}
        if t>=1.0{return b;}
        match curve.segments[i].curve{
            Curve::Line=>mix(a,b,t),
            Curve::Arc{center,clockwise}=>{
                split(a,b,Curve::Arc{center,clockwise},t).unwrap().0
            }
            Curve::Cubic{control1:c,control2:d}=>{
                let u=1.0-t;
                Point::new(u*u*u*a.x+3.0*u*u*t*c.x+3.0*u*t*t*d.x+t*t*t*b.x,
                    u*u*u*a.y+3.0*u*u*t*c.y+3.0*u*t*t*d.y+t*t*t*b.y)
            }
        }
    }
    #[test]
    fn split_preserves_line_arc_and_cubic_exact_positions(){
        for kind in [Primitive::Line,Primitive::Arc,Primitive::Cubic]{
            let p=demo(kind);
            let (q,node_id)=split_segment(&p,p.segments[0].id,0.3).unwrap();
            assert_eq!(q.segments.len(),2);
            assert_eq!(q.nodes.len(),3);
            assert_eq!(q.segments[0].id,p.segments[0].id);
            assert_eq!(q.nodes[1].id,node_id);
            for t in [0.03,0.19,0.3,0.41,0.78,0.99]{
                let (seg,local)=if t<=0.3{(0,t/0.3)}else{(1,(t-0.3)/0.7)};
                assert!(dist(point_on(&p,0,t),point_on(&q,seg,local))<1e-7);
            }
            q.validate().unwrap();
        }
    }
    #[test]
    fn trim_cubic_and_arc_remain_source_exact(){
        for kind in [Primitive::Arc,Primitive::Cubic]{
            let p=demo(kind);
            let first=trim_endpoint(&p,true,0.2).unwrap();
            let last=trim_endpoint(&p,false,0.7).unwrap();
            for t in [0.0,0.15,0.7,1.0]{
                assert!(dist(point_on(&p,0,0.2+t*0.8),
                    point_on(&first,0,t))<1e-7);
                assert!(dist(point_on(&p,0,t*0.7),
                    point_on(&last,0,t))<1e-7);
            }
        }
    }
    #[test]
    fn joining_reorients_cubic_and_circular_arc_without_flattening(){
        let a=demo(Primitive::Arc);
        let mut b=demo(Primitive::Cubic);
        b.origin=Point::new(52.0,15.0);
        let joined=join_open(&a,&b,0.0).unwrap();
        assert_eq!(joined.nodes.len(),3);
        assert_eq!(joined.segments.len(),2);
        assert!(matches!(joined.segments[0].curve,Curve::Arc{..}));
        assert!(matches!(joined.segments[1].curve,Curve::Cubic{..}));
        let orig_end=point_on(&b,0,0.76).offset(b.origin.x,b.origin.y);
        let new_end=point_on(&joined,1,0.76).offset(joined.origin.x,joined.origin.y);
        assert!(dist(orig_end,new_end)<1e-8);
        let backward=join_open(&a,&reversed(b.clone()),0.0).unwrap();
        assert_eq!(backward.nodes.len(),3);
        assert!(matches!(backward.segments[1].curve,Curve::Cubic{..}));
    }
    #[test]
    fn extending_and_offsetting_never_sampling_curves(){
        let p=demo(Primitive::Line);
        let e=extend_line(&p,true,5.0).unwrap();
        assert_eq!(e.nodes[0].position,Point::new(-5.0,0.0));
        let shifted=offset_lines(&p,4.0).unwrap();
        assert_eq!(shifted.nodes[0].position,Point::new(0.0,4.0));
        assert!(offset_lines(&demo(Primitive::Cubic),5.0).is_err());
        let square=create_shape(1,"Square".into(),Point::new(5.0,5.0),
            ShapeKind::Rectangle,20.0,20.0).unwrap();
        let outer=offset_lines(&square,2.0).unwrap();
        assert!((outer.nodes[0].position.x+2.0).abs()<1e-7);
        assert!((outer.nodes[0].position.y+2.0).abs()<1e-7);
        outer.validate().unwrap();
    }
    #[test]
    fn fillet_and_chamfer_preserve_straights_and_exact_circle(){
        let mut p=demo(Primitive::Line);
        p.nodes.push(PathNode{id:4,position:Point::new(40.0,40.0)});
        p.segments.push(PathSegment{id:5,curve:Curve::Line});
        p.next_element_id=6;
        p.validate().unwrap();
        let bevel=corner(&p,2,5.0,false).unwrap();
        assert_eq!(bevel.nodes.len(),4);
        assert!(matches!(bevel.segments[1].curve,Curve::Line));
        let fillet=corner(&p,2,5.0,true).unwrap();
        assert!(matches!(fillet.segments[1].curve,Curve::Arc{..}));
        assert!(corner(&p,1,5.0,true).is_err());
        assert!(corner(&p,2,100.0,true).is_err());
        fillet.validate().unwrap();
    }
    #[test]
    fn closed_rectangle_corner_operations_validate_and_keep_loop(){
        let rectangle=create_shape(1,"Rect".into(),Point::new(10.0,10.0),
            ShapeKind::Rectangle,50.0,30.0).unwrap();
        for node_id in [1_u64,3_u64,4_u64]{
            for fillet in [false,true]{
                let edited=corner(&rectangle,node_id,3.0,fillet).unwrap();
                assert!(edited.closed);
                assert_eq!(edited.nodes.len(),5);
                assert_eq!(edited.segments.len(),5);
                assert!(edited.segments.iter().any(|s|
                    matches!(s.curve,Curve::Arc{..}))==fillet);
                edited.validate().unwrap();
            }
        }
        assert!(corner(&rectangle,1,50.0,true).is_err());
        assert_eq!(rectangle.nodes.len(),4);
    }
    #[test]
    fn circular_arc_and_concentric_circle_offsets_retain_true_radius(){
        let mut arc=demo(Primitive::Arc);
        let Curve::Arc{center,clockwise}=arc.segments[0].curve else{panic!("Arc");};
        let radius=dist(arc.nodes[0].position,center);
        let offset=offset_exact(&arc,4.0).unwrap();
        assert!(matches!(offset.segments[0].curve,Curve::Arc{..}));
        assert!((dist(offset.nodes[0].position,center)-radius
            -if clockwise{4.0}else{-4.0}).abs()<1e-8);
        assert_eq!(arc.nodes[0].position,Point::new(0.0,0.0));
        assert!(offset_exact(&arc,-100.0).is_err());
        let r=12.0;let c=Point::new(10.0,12.0);
        arc.nodes=vec![
            Point::new(c.x+r,c.y),Point::new(c.x,c.y+r),
            Point::new(c.x-r,c.y),Point::new(c.x,c.y-r)
        ].into_iter().enumerate().map(|(i,position)|
            PathNode{id:i as u64+1,position}).collect();
        arc.segments=(0..4).map(|i|PathSegment{id:i+5,
            curve:Curve::Arc{center:c,clockwise:false}}).collect();
        arc.closed=true;arc.next_element_id=9;
        arc.validate().unwrap();
        let outer=offset_exact(&arc,3.0).unwrap();
        assert!(outer.closed);
        assert!((dist(outer.nodes[0].position,c)-15.0).abs()<1e-8);
        assert!(outer.segments.iter().all(|s|matches!(s.curve,Curve::Arc{..})));
    }
    #[test]
    fn rejects_invalid_or_unsafe_geometry_without_mutating_sources(){
        let p=demo(Primitive::Arc);
        let original=p.clone();
        assert!(split_segment(&p,3,0.0).is_err());
        assert!(extend_line(&p,true,5.0).is_err());
        assert!(offset_lines(&p,3.0).is_err());
        let mut distant=demo(Primitive::Cubic);
        distant.origin=Point::new(200.0,100.0);
        assert!(join_open(&p,&distant,0.05).is_err());
        assert_eq!(p,original);
    }
}
