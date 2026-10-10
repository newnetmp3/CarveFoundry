//! Bounded source-geometry intersections involving cubic Bézier segments.
//!
//! Line and circle pairs use true polynomial roots (degrees 3 and 6).
//! Cubic/cubic pairs use control-hull interval subdivision, validated
//! against the actual curves with a damped Newton refinement. No preview
//! polylines are consulted or stored. Unresolved overlap fails closed.
use crate::Point;
use std::f64::consts::TAU;

const POSITION_EPS:f64=1e-6;
const ROOT_EPS:f64=2e-11;
const PARAM_EPS:f64=1e-9;
const MAX_SUBDIVISIONS:usize=250_000;
const MAX_DEPTH:u8=58;

fn add(a:Point,b:Point)->Point{Point::new(a.x+b.x,a.y+b.y)}
fn sub(a:Point,b:Point)->Point{Point::new(a.x-b.x,a.y-b.y)}
fn mul(a:Point,k:f64)->Point{Point::new(a.x*k,a.y*k)}
fn dot(a:Point,b:Point)->f64{a.x*b.x+a.y*b.y}
fn cross(a:Point,b:Point)->f64{a.x*b.y-a.y*b.x}
fn norm(a:Point)->f64{a.x.hypot(a.y)}
fn dist(a:Point,b:Point)->f64{norm(sub(a,b))}
fn mix(a:Point,b:Point,t:f64)->Point{add(mul(a,1.0-t),mul(b,t))}
fn eval(c:[Point;4],t:f64)->Point{
    let u=1.0-t;
    add(add(mul(c[0],u*u*u),mul(c[1],3.0*u*u*t)),
        add(mul(c[2],3.0*u*t*t),mul(c[3],t*t*t)))
}
fn derivative(c:[Point;4],t:f64)->Point{
    let u=1.0-t;
    add(add(mul(sub(c[1],c[0]),3.0*u*u),
        mul(sub(c[2],c[1]),6.0*u*t)),mul(sub(c[3],c[2]),3.0*t*t))
}
fn poly_eval(coeff:&[f64],t:f64)->f64{
    coeff.iter().rev().fold(0.0,|sum,c|sum*t+c)
}
fn unique(ts:&mut Vec<f64>,eps:f64){
    ts.sort_by(f64::total_cmp);
    ts.dedup_by(|a,b|(*a-*b).abs()<eps);
}
/// Complete real roots of a small polynomial on [0,1].
/// Recursively partitions at derivative critical points, so even-multiplicity
/// (tangent) roots are inspected rather than skipped by a sign-only scan.
fn unit_roots(coeff:&[f64])->Result<Vec<f64>,()>{
    let magnitude=coeff.iter().map(|v|v.abs()).fold(0.0,f64::max);
    if !magnitude.is_finite()||magnitude<1e-28{return Err(());}
    let mut normalized=coeff.iter().map(|v|*v/magnitude).collect::<Vec<_>>();
    while normalized.len()>1 && normalized.last().is_some_and(|v|v.abs()<1e-14){
        normalized.pop();
    }
    if normalized.len()==1 {
        return if normalized[0].abs()<ROOT_EPS{Err(())}else{Ok(Vec::new())};
    }
    if normalized.len()==2 {
        let t=-normalized[0]/normalized[1];
        return Ok(if (-PARAM_EPS..=1.0+PARAM_EPS).contains(&t){
            vec![t.clamp(0.0,1.0)]
        }else{Vec::new()});
    }
    let derivative=normalized.iter().enumerate().skip(1)
        .map(|(i,v)|*v*i as f64).collect::<Vec<_>>();
    let mut divisions=unit_roots(&derivative).unwrap_or_default();
    divisions.push(0.0);divisions.push(1.0);
    unique(&mut divisions,1e-10);
    let mut roots=Vec::new();
    for &t in &divisions{
        if poly_eval(&normalized,t).abs()<=ROOT_EPS{roots.push(t);}
    }
    for range in divisions.windows(2){
        let mut lo=range[0];let mut hi=range[1];
        let mut vlo=poly_eval(&normalized,lo);
        let vhi=poly_eval(&normalized,hi);
        if (vlo>0.0)==(vhi>0.0)||vlo.abs()<ROOT_EPS||vhi.abs()<ROOT_EPS{
            continue;
        }
        for _ in 0..75{
            let mid=0.5*(lo+hi);
            let value=poly_eval(&normalized,mid);
            if (value>0.0)==(vlo>0.0){
                lo=mid;vlo=value;
            }else{hi=mid;}
        }
        roots.push(0.5*(lo+hi));
    }
    unique(&mut roots,1e-8);
    Ok(roots)
}
fn cubic_power(c:[Point;4])->[Point;4]{
    [c[0],
    add(sub(mul(c[1],3.0),mul(c[0],3.0)),Point::new(0.0,0.0)),
    add(add(mul(c[0],3.0),mul(c[2],3.0)),mul(c[1],-6.0)),
    add(add(mul(c[1],3.0),mul(c[3],1.0)),
        add(mul(c[0],-1.0),mul(c[2],-3.0)))]
}
fn push_unique(hits:&mut Vec<(Point,f64,f64)>,p:Point,t:f64,u:f64){
    if !p.finite()||!t.is_finite()||!u.is_finite(){return;}
    if hits.iter().any(|(q,s,v)|dist(*q,p)<1e-6
        && (s-t).abs()<1e-5&&(v-u).abs()<1e-5){return;}
    hits.push((p,t,u));
}
/// Returns cubic fraction followed by straight-line fraction.
pub(crate) fn cubic_line(c:[Point;4],a:Point,b:Point)
    ->(Vec<(Point,f64,f64)>,bool){
    let line=sub(b,a);let len2=dot(line,line);
    if len2<1e-16{return (Vec::new(),true);}
    let coeff=cubic_power(c).map(|p|cross(p,line));
    let coeff=[coeff[0]-cross(a,line),coeff[1],coeff[2],coeff[3]];
    let roots=match unit_roots(&coeff){
        Ok(roots)=>roots,Err(())=>return (Vec::new(),true)
    };
    let mut hits=Vec::new();
    for t in roots{
        let p=eval(c,t);
        let u=dot(sub(p,a),line)/len2;
        if (-PARAM_EPS..=1.0+PARAM_EPS).contains(&u)
            && cross(sub(p,a),line).abs()/len2.sqrt()<=POSITION_EPS{
            push_unique(&mut hits,p,t,u.clamp(0.0,1.0));
        }
    }
    (hits,false)
}
fn arc_param(start:Point,end:Point,center:Point,clockwise:bool,
    p:Point)->Option<f64>{
    let r=dist(start,center);
    if r<1e-9 || (dist(p,center)-r).abs()>POSITION_EPS {
        return None;
    }
    let a=(start.y-center.y).atan2(start.x-center.x);
    let b=(end.y-center.y).atan2(end.x-center.x);
    let theta=(p.y-center.y).atan2(p.x-center.x);
    let sweep=if clockwise{(a-b).rem_euclid(TAU)}else{(b-a).rem_euclid(TAU)};
    let along=if clockwise{(a-theta).rem_euclid(TAU)}
        else{(theta-a).rem_euclid(TAU)};
    if sweep<1e-11 || along>sweep+1e-8{return None;}
    Some((along/sweep).clamp(0.0,1.0))
}
/// Degree-6 intersection polynomial: (Bezier(t) - center)^2 - radius².
/// Analytic power-basis operations, not sampled curve flattening.
pub(crate) fn cubic_arc(c:[Point;4],start:Point,end:Point,
    center:Point,clockwise:bool)->(Vec<(Point,f64,f64)>,bool){
    let r=dist(start,center);
    if r<1e-9{return (Vec::new(),true);}
    let mut p=cubic_power(c);
    p[0]=sub(p[0],center);
    let mut coeff=[0.0;7];
    for i in 0..4{
        for j in 0..4{
            coeff[i+j]+=dot(p[i],p[j]);
        }
    }
    coeff[0]-=r*r;
    let roots=match unit_roots(&coeff){
        Ok(roots)=>roots,Err(())=>return (Vec::new(),true)
    };
    let mut hits=Vec::new();
    for t in roots {
        let q=eval(c,t);
        if let Some(u)=arc_param(start,end,center,clockwise,q){
            push_unique(&mut hits,q,t,u);
        }
    }
    (hits,false)
}
#[derive(Clone,Copy)]
struct Piece{
    c:[Point;4],lo:f64,hi:f64,
}
impl Piece{
    fn full(c:[Point;4])->Self{Self{c,lo:0.0,hi:1.0}}
    fn split(self)->(Self,Self){
        let c=self.c;
        let a=mix(c[0],c[1],0.5);
        let b=mix(c[1],c[2],0.5);
        let d=mix(c[2],c[3],0.5);
        let e=mix(a,b,0.5);
        let f=mix(b,d,0.5);
        let mid=mix(e,f,0.5);
        let t=(self.lo+self.hi)*0.5;
        (Self{c:[c[0],a,e,mid],lo:self.lo,hi:t},
         Self{c:[mid,f,d,c[3]],lo:t,hi:self.hi})
    }
    fn bounds(self)->(Point,Point){
        let min=Point::new(self.c.iter().map(|p|p.x).fold(f64::INFINITY,f64::min),
            self.c.iter().map(|p|p.y).fold(f64::INFINITY,f64::min));
        let max=Point::new(self.c.iter().map(|p|p.x).fold(f64::NEG_INFINITY,f64::max),
            self.c.iter().map(|p|p.y).fold(f64::NEG_INFINITY,f64::max));
        (min,max)
    }
    fn extent(self)->f64{
        let (min,max)=self.bounds();
        norm(sub(max,min))
    }
}
fn hulls_overlap(a:Piece,b:Piece)->bool{
    let (a0,a1)=a.bounds();let (b0,b1)=b.bounds();
    !(a1.x+POSITION_EPS<b0.x||b1.x+POSITION_EPS<a0.x||
        a1.y+POSITION_EPS<b0.y||b1.y+POSITION_EPS<a0.y)
}
fn newton(a:[Point;4],b:[Point;4],t:f64,u:f64)->Option<(Point,f64,f64)>{
    let mut t=t;let mut u=u;
    for _ in 0..22{
        let pa=eval(a,t);let pb=eval(b,u);
        let gap=sub(pa,pb);
        if norm(gap)<1e-8{
            return Some((mul(add(pa,pb),0.5),t,u));
        }
        let da=derivative(a,t);let db=derivative(b,u);
        let det=cross(da,db);
        if det.abs()<1e-15*norm(da).max(1.0)*norm(db).max(1.0){
            break;
        }
        let dt=-cross(gap,db)/det;
        let du=-cross(gap,da)/det;
        if !dt.is_finite()||!du.is_finite(){break;}
        // Prevent wild steps; a bad local estimate is not a valid crossing.
        t+=dt.clamp(-0.15,0.15);
        u+=du.clamp(-0.15,0.15);
        if !(-0.001..=1.001).contains(&t)||!(-0.001..=1.001).contains(&u){
            break;
        }
    }
    let pa=eval(a,t);let pb=eval(b,u);
    if norm(sub(pa,pb))<=1e-7 &&
        (-PARAM_EPS..=1.0+PARAM_EPS).contains(&t)&&
        (-PARAM_EPS..=1.0+PARAM_EPS).contains(&u){
        Some((mul(add(pa,pb),0.5),t.clamp(0.0,1.0),u.clamp(0.0,1.0)))
    }else{None}
}
/// Source-faithful cubic/cubic intersections using geometric interval boxes.
/// Bounding boxes enclose the WHOLE Bézier hull on each interval; isolated
/// candidate roots are refined and checked against original source cubics.
/// Recursive limit is explicit; unresolved near-overlap reports unsupported.
pub(crate) fn cubic_cubic(a:[Point;4],b:[Point;4])
    ->(Vec<(Point,f64,f64)>,bool){
    // Exact duplicate and reversed duplicate source curves have infinitely
    // many intersections: do not produce a false finite marker list.
    if (0..4).all(|i|dist(a[i],b[i])<1e-8)
        || (0..4).all(|i|dist(a[i],b[3-i])<1e-8){
        return (Vec::new(),true);
    }
    let mut hits=Vec::new();
    let mut stack=vec![(Piece::full(a),Piece::full(b),0_u8)];
    let mut visits=0;
    let mut incomplete=false;
    while let Some((left,right,depth))=stack.pop(){
        visits+=1;
        if visits>MAX_SUBDIVISIONS{
            incomplete=true;
            break;
        }
        if !hulls_overlap(left,right){continue;}
        let extent_left=left.extent();
        let extent_right=right.extent();
        if (extent_left<=1e-5 && extent_right<=1e-5)||depth>=MAX_DEPTH{
            if let Some((p,t,u))=newton(a,b,(left.lo+left.hi)*0.5,
                (right.lo+right.hi)*0.5){
                push_unique(&mut hits,p,t,u);
            }else if depth>=MAX_DEPTH{
                incomplete=true;
            }
            continue;
        }
        if extent_left>=extent_right{
            let (l,r)=left.split();
            stack.push((r,right,depth+1));
            stack.push((l,right,depth+1));
        }else{
            let (l,r)=right.split();
            stack.push((left,r,depth+1));
            stack.push((left,l,depth+1));
        }
    }
    if incomplete {
        // Do not advertise an incomplete set of crossings as exhaustive.
        return (Vec::new(),true);
    }
    hits.sort_by(|x,y|x.1.total_cmp(&y.1));
    (hits,false)
}

#[cfg(test)]
mod tests{
    use super::*;
    fn linear(a:Point,b:Point)->[Point;4]{
        [a,mix(a,b,1.0/3.0),mix(a,b,2.0/3.0),b]
    }
    #[test]
    fn cubic_line_has_two_intersections_and_reversed_params(){
        let curve=[Point::new(0.0,0.0),Point::new(0.0,10.0),
            Point::new(10.0,10.0),Point::new(10.0,0.0)];
        let (hits,bad)=cubic_line(curve,Point::new(-1.0,5.0),
            Point::new(11.0,5.0));
        assert!(!bad);
        assert_eq!(hits.len(),2);
        assert!(hits[0].1<hits[1].1);
        for (p,t,u) in hits{
            assert!((p.y-5.0).abs()<1e-7);
            assert!((eval(curve,t).x-p.x).abs()<1e-7);
            assert!(((-1.0+12.0*u)-p.x).abs()<1e-7);
        }
    }
    #[test]
    fn cubic_line_detects_tangent_even_without_sign_change(){
        let curve=[Point::new(-1.0,1.0),Point::new(-0.3,-1.0/3.0),
            Point::new(0.3,-1.0/3.0),Point::new(1.0,1.0)];
        let (hits,bad)=cubic_line(curve,Point::new(-3.0,0.0),
            Point::new(3.0,0.0));
        assert!(!bad);
        assert_eq!(hits.len(),1);
        assert!((hits[0].1-0.5).abs()<1e-8);
        assert!(hits[0].0.y.abs()<1e-8);
    }
    #[test]
    fn cubic_circle_respects_sweep_and_root_geometry(){
        let cubic=linear(Point::new(-2.0,-2.0),Point::new(2.0,2.0));
        let (hits,bad)=cubic_arc(cubic,Point::new(-1.0,0.0),
            Point::new(1.0,0.0),Point::new(0.0,0.0),true);
        assert!(!bad);
        assert_eq!(hits.len(),1);
        assert!(hits[0].0.x>0.7 && hits[0].0.y>0.7);
        assert!((norm(hits[0].0)-1.0).abs()<1e-7);
    }
    #[test]
    fn cubic_cubic_crossing_multiple_roots_and_exact_overlap(){
        let a=linear(Point::new(-3.0,0.0),Point::new(3.0,0.0));
        let b=linear(Point::new(0.0,-3.0),Point::new(0.0,3.0));
        let (hits,bad)=cubic_cubic(a,b);
        assert!(!bad);
        assert_eq!(hits.len(),1);
        assert!(norm(hits[0].0)<1e-6);
        let arch=[Point::new(0.0,0.0),Point::new(0.0,10.0),
            Point::new(10.0,10.0),Point::new(10.0,0.0)];
        let line=linear(Point::new(-1.0,5.0),Point::new(11.0,5.0));
        let (hits,bad)=cubic_cubic(arch,line);
        assert!(!bad);
        assert_eq!(hits.len(),2);
        let (none,unsupported)=cubic_cubic(arch,arch);
        assert!(unsupported&&none.is_empty());
    }
    #[test]
    fn cubic_circle_tangent_still_deduplicates(){
        let arc=linear(Point::new(-2.0,1.0),Point::new(2.0,1.0));
        let (hits,bad)=cubic_arc(arc,Point::new(-1.0,0.0),
            Point::new(1.0,0.0),Point::new(0.0,0.0),true);
        assert!(!bad);
        assert_eq!(hits.len(),1);
        assert!(hits[0].0.x.abs()<1e-8);
    }
    #[test]
    fn collinear_cubic_line_is_flagged_as_nonfinite_overlap(){
        let curve=linear(Point::new(-3.0,0.0),Point::new(3.0,0.0));
        let (hits,bad)=cubic_line(curve,Point::new(-1.0,0.0),
            Point::new(1.0,0.0));
        assert!(bad&&hits.is_empty());
    }
}
