//! Retained analytic 2D paths. Never persist a sampled approximation of an arc
//! or cubic curve as the design source. Preview sampling is visual-only.
use crate::geometry::{Point, signed_area};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::f64::consts::TAU;

const EPS: f64 = 1e-8;
const MAX_NODES: usize = 256;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Primitive { Line, Arc, Cubic }

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PathNode {
    pub id: u64,
    pub position: Point,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Curve {
    Line,
    Arc { center: Point, clockwise: bool },
    Cubic { control1: Point, control2: Point },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PathSegment {
    pub id: u64,
    pub curve: Curve,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AnalyticPath {
    pub id: u64,
    pub name: String,
    pub origin: Point,
    pub visible: bool,
    pub locked: bool,
    pub closed: bool,
    /// Endpoints are shared nodes, in path order. Segment i joins node i
    /// to node i+1 (or node zero when closed). Node/segment IDs are stable.
    pub nodes: Vec<PathNode>,
    pub segments: Vec<PathSegment>,
    pub next_element_id: u64,
}

fn distance(a: Point, b: Point) -> f64 { (a.x-b.x).hypot(a.y-b.y) }

impl AnalyticPath {
    pub fn preset(id: u64, name: String, origin: Point, kind: Primitive,
        width: f64, height: f64) -> Result<Self,String> {
        if !width.is_finite() || !height.is_finite()
            || !(0.1..=10_000.0).contains(&width)
            || !(0.1..=10_000.0).contains(&height) {
            return Err("Path dimensions must be finite and between 0.1 and 10,000 mm".into());
        }
        let curve=match kind {
            Primitive::Line => Curve::Line,
            Primitive::Arc => Curve::Arc {center:Point::new(width*0.5,0.0),clockwise:true},
            Primitive::Cubic => Curve::Cubic {
                control1:Point::new(width*0.25,height),
                control2:Point::new(width*0.75,height),
            },
        };
        let p=Self {
            id,name,origin,visible:true,locked:false,closed:false,
            nodes:vec![
                PathNode{id:1,position:Point::new(0.0,0.0)},
                PathNode{id:2,position:Point::new(width,0.0)},
            ],
            segments:vec![PathSegment{id:3,curve}],
            next_element_id:4,
        };
        p.validate()?;
        Ok(p)
    }

    fn endpoints(&self, index: usize) -> (Point,Point) {
        (self.nodes[index].position,
            self.nodes[(index+1)%self.nodes.len()].position)
    }

    pub fn validate(&self) -> Result<(),String> {
        if self.id==0 || self.name.trim().is_empty() || self.name.len()>256
            || !self.origin.finite() || self.next_element_id==0
            || !(2..=MAX_NODES).contains(&self.nodes.len())
            || (self.closed && self.nodes.len()<3)
            || self.segments.len()!=self.nodes.len()-usize::from(!self.closed) {
            return Err("Invalid analytic path identity, node or segment count".into());
        }
        let mut used=HashSet::new();
        for node in &self.nodes {
            if node.id==0 || node.id>=self.next_element_id
                || !used.insert(node.id) || !node.position.finite()
                || !node.position.offset(self.origin.x,self.origin.y).finite() {
                return Err("Invalid/repeated/out-of-bounds analytic node".into());
            }
        }
        for (i,segment) in self.segments.iter().enumerate() {
            if segment.id==0 || segment.id>=self.next_element_id || !used.insert(segment.id) {
                return Err("Invalid/repeated analytic segment identity".into());
            }
            let (a,b)=self.endpoints(i);
            if distance(a,b)<EPS {
                return Err("Analytic segment has identical endpoints".into());
            }
            match segment.curve {
                Curve::Line=>{},
                Curve::Arc{center,..} => {
                    if !center.finite() || !center.offset(self.origin.x,self.origin.y).finite() {
                        return Err("Nonfinite or out-of-bounds circular arc center".into());
                    }
                    let r1=distance(a,center);
                    let r2=distance(b,center);
                    if r1<EPS || (r1-r2).abs()>r1.max(1.0)*1e-7 {
                        return Err("Circular arc endpoints must share one true center/radius".into());
                    }
                },
                Curve::Cubic{control1,control2} => {
                    if !control1.finite() || !control2.finite()
                        || !control1.offset(self.origin.x,self.origin.y).finite()
                        || !control2.offset(self.origin.x,self.origin.y).finite() {
                        return Err("Cubic Bézier control points exceed finite bounds".into());
                    }
                },
            }
        }
        if self.closed {
            let sample=self.preview_points(0.25)?;
            if signed_area(&sample).abs()<EPS {
                return Err("Closed analytic path has zero signed area".into());
            }
        }
        Ok(())
    }

    /// Visual polygonal preview ONLY, never used to rewrite the analytic
    /// source or authorize machining. Each arc has at most 128 steps.
    pub fn preview_points(&self, tolerance_mm: f64) -> Result<Vec<Point>,String> {
        if !tolerance_mm.is_finite() || !(0.02..=10.0).contains(&tolerance_mm)
            || self.nodes.len()>MAX_NODES
            || self.segments.len()>MAX_NODES {
            return Err("Invalid preview tolerance or excessively large path".into());
        }
        let mut out=Vec::with_capacity(self.segments.len()*32+1);
        for (i,s) in self.segments.iter().enumerate() {
            let (a,b)=self.endpoints(i);
            if out.is_empty(){out.push(a.offset(self.origin.x,self.origin.y));}
            match s.curve {
                Curve::Line => out.push(b.offset(self.origin.x,self.origin.y)),
                Curve::Arc{center,clockwise} => {
                    let r=distance(a,center);
                    if !r.is_finite() || r<EPS || (r-distance(b,center)).abs()>r.max(1.0)*1e-7 {
                        return Err("Inconsistent circular arc geometry".into());
                    }
                    let angle_a=(a.y-center.y).atan2(a.x-center.x);
                    let angle_b=(b.y-center.y).atan2(b.x-center.x);
                    let sweep=if clockwise {
                        -((angle_a-angle_b).rem_euclid(TAU))
                    }else{(angle_b-angle_a).rem_euclid(TAU)};
                    if sweep.abs()<EPS {return Err("Circular arc has zero sweep".into());}
                    let unit=(1.0-tolerance_mm/r).clamp(-1.0,1.0);
                    let angle_step=2.0*unit.acos();
                    let steps=if angle_step<EPS {128}
                        else{(sweep.abs()/angle_step).ceil().clamp(1.0,128.0) as usize};
                    for k in 1..=steps {
                        if k==steps {out.push(b.offset(self.origin.x,self.origin.y));}
                        else {
                            let angle=angle_a+sweep*(k as f64/steps as f64);
                            out.push(Point::new(
                                center.x+r*angle.cos(),center.y+r*angle.sin(),
                            ).offset(self.origin.x,self.origin.y));
                        }
                    }
                },
                Curve::Cubic{control1,control2} => {
                    // 32 visual subdivisions; exact control points remain stored.
                    for k in 1..=32 {
                        let t=k as f64/32.0;
                        let u=1.0-t;
                        let p=Point::new(
                            u*u*u*a.x+3.0*u*u*t*control1.x+3.0*u*t*t*control2.x+t*t*t*b.x,
                            u*u*u*a.y+3.0*u*u*t*control1.y+3.0*u*t*t*control2.y+t*t*t*b.y,
                        );
                        out.push(p.offset(self.origin.x,self.origin.y));
                    }
                },
            }
        }
        if out.iter().any(|p|!p.finite()){return Err("Analytic preview exceeded bounds".into());}
        Ok(out)
    }

    fn node_index(&self,id:u64)->Result<usize,String> {
        self.nodes.iter().position(|n|n.id==id).ok_or("Unknown path node identity".into())
    }

    /// Moving a cubic endpoint translates its adjacent control handles.
    /// Arc endpoints stay locked until a constraint-preserving arc editor exists.
    /// Refit the original circular sweep to the new chord, rather than
    /// rejecting every arc anchor drag. The arc remains an exact circle.
    fn refitted_arc_center(a:Point,b:Point,center:Point,clockwise:bool,
        new_a:Point,new_b:Point)->Result<Point,String>{
        let begin=(a.y-center.y).atan2(a.x-center.x);
        let end=(b.y-center.y).atan2(b.x-center.x);
        let sweep=if clockwise {
            (begin-end).rem_euclid(TAU)
        }else{
            (end-begin).rem_euclid(TAU)
        };
        let dx=new_b.x-new_a.x;let dy=new_b.y-new_a.y;
        let chord=dx.hypot(dy);
        if chord<EPS || sweep<EPS || (TAU-sweep)<EPS {
            return Err("Arc endpoints or sweep are degenerate".into());
        }
        let middle=Point::new((new_a.x+new_b.x)*0.5,(new_a.y+new_b.y)*0.5);
        let tan=(sweep*0.5).tan();
        let altitude=if !tan.is_finite(){0.0}else{chord/(2.0*tan)}
            *if clockwise{-1.0}else{1.0};
        let candidate=Point::new(middle.x-dy/chord*altitude,
            middle.y+dx/chord*altitude);
        if !candidate.finite() {return Err("Refitted arc exceeds design coordinates".into());}
        Ok(candidate)
    }

    /// Anchor motions are atomic: cubic adjacent handles translate with the
    /// endpoint, while circular arcs preserve their signed sweep and recompute
    /// the exact center/radius for the new chord.
    pub fn move_node(&mut self,id:u64,point:Point)->Result<(),String>{
        let mut draft=self.clone();
        let i=draft.node_index(id)?;
        let prior=draft.nodes[i].position;
        if prior==point{return Ok(());}
        let n=draft.nodes.len();
        let incoming=if i>0{Some(i-1)}else if draft.closed{Some(n-1)}else{None};
        let outgoing=if i<draft.segments.len(){Some(i)}else{None};
        type ArcSnapshot=(usize,Point,Point,Point,bool);
        let old_arcs:[Option<ArcSnapshot>;2]=
            [incoming,outgoing].map(|index|index.and_then(|j|{
                let (a,b)=draft.endpoints(j);
                match draft.segments[j].curve {
                    Curve::Arc{center,clockwise}=>Some((j,a,b,center,clockwise)),
                    _=>None
                }
            }));
        let dx=point.x-prior.x;let dy=point.y-prior.y;
        if let Some(j)=incoming
            && let Curve::Cubic{ref mut control2,..}=draft.segments[j].curve{
                *control2=control2.offset(dx,dy);
            }
        if let Some(j)=outgoing
            && let Curve::Cubic{ref mut control1,..}=draft.segments[j].curve{
                *control1=control1.offset(dx,dy);
            }
        draft.nodes[i].position=point;
        for (j,a,b,center,clockwise) in old_arcs.into_iter().flatten(){
            let (new_a,new_b)=draft.endpoints(j);
            let new_center=Self::refitted_arc_center(
                a,b,center,clockwise,new_a,new_b)?;
            draft.segments[j].curve=Curve::Arc{center:new_center,clockwise};
        }
        draft.validate()?;
        *self=draft;
        Ok(())
    }

    pub fn move_control(&mut self,segment_id:u64,handle:u8,point:Point)
        -> Result<(),String>{
        let mut draft=self.clone();
        let segment=draft.segments.iter_mut().find(|s|s.id==segment_id)
            .ok_or("Unknown path segment identity")?;
        match &mut segment.curve {
            Curve::Cubic{control1,control2} => match handle{
                1=>*control1=point,
                2=>*control2=point,
                _=>return Err("Cubic handle must be 1 or 2".into()),
            },
            _=>return Err("Only cubic segments have handles".into()),
        }
        draft.validate()?;
        *self=draft;
        Ok(())
    }

    /// Splits a LINE at its midpoint, retaining its original segment ID on
    /// the left; never approximates a cubic/arc to introduce a node.
    pub fn split_line_after(&mut self, node_id:u64) -> Result<u64,String> {
        let i=self.node_index(node_id)?;
        if i>=self.segments.len() || !matches!(self.segments[i].curve,Curve::Line) {
            return Err("Node insertion currently requires an existing line edge".into());
        }
        if self.nodes.len()>=MAX_NODES {return Err("Maximum analytic nodes reached".into());}
        let id=self.next_element_id;
        self.next_element_id=self.next_element_id.checked_add(2).ok_or("Element IDs exhausted")?;
        let (a,b)=self.endpoints(i);
        let mid=Point::new((a.x+b.x)*0.5,(a.y+b.y)*0.5);
        self.nodes.insert(i+1,PathNode{id,position:mid});
        self.segments.insert(i+1,PathSegment{id:id+1,curve:Curve::Line});
        self.validate()?;
        Ok(id)
    }

    /// Only line-line joins may delete an interior node. No silent change
    /// of an analytic arc/cubic when removing their shared endpoint.
    pub fn remove_node(&mut self,node_id:u64) -> Result<(),String> {
        let index=self.node_index(node_id)?;
        if self.nodes.len()<=if self.closed{3}else{2} {
            return Err("Cannot remove the final required analytic nodes".into());
        }
        let n=self.nodes.len();
        let incoming=if index>0{Some(index-1)}else if self.closed{Some(n-1)}else{None};
        let outgoing=if index<self.segments.len(){Some(index)}else{None};
        for j in [incoming,outgoing].into_iter().flatten() {
            if !matches!(self.segments[j].curve,Curve::Line) {
                return Err("Only line-only junctions can be removed losslessly".into());
            }
        }
        let segment_to_remove=outgoing.unwrap_or_else(||index-1);
        self.segments.remove(segment_to_remove);
        self.nodes.remove(index);
        self.validate()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn p(kind:Primitive)->AnalyticPath {
        AnalyticPath::preset(9,"Curve".into(),Point::new(10.0,5.0),
            kind,50.0,30.0).unwrap()
    }
    #[test]
    fn retained_segment_types_roundtrip_without_flattening() {
        for kind in [Primitive::Line,Primitive::Arc,Primitive::Cubic] {
            let path=p(kind);
            let serialized=serde_json::to_vec(&path).unwrap();
            let parsed:AnalyticPath=serde_json::from_slice(&serialized).unwrap();
            assert_eq!(parsed,path);
            assert!(path.preview_points(0.25).unwrap().len()>=2);
        }
    }
    #[test]
    fn arc_sweep_is_bounded_and_endpoints_exact() {
        let path=p(Primitive::Arc);
        let pts=path.preview_points(0.25).unwrap();
        assert!(pts.len()<=129);
        assert_eq!(pts.first().unwrap(),&Point::new(10.0,5.0));
        assert_eq!(pts.last().unwrap(),&Point::new(60.0,5.0));
        assert!(pts.iter().any(|v|v.y>5.0));
    }
    #[test]
    fn rejects_nonconcentric_arc_and_nonfinite_controls() {
        let mut a=p(Primitive::Arc);
        a.nodes[1].position.y=3.0;
        assert!(a.validate().is_err());
        let mut b=p(Primitive::Cubic);
        b.move_control(3,1,Point::new(f64::NAN,0.0)).unwrap_err();
        let mut b=p(Primitive::Cubic);
        b.next_element_id=3;
        assert!(b.validate().is_err());
    }
    #[test]
    fn preserves_handles_when_moving_an_anchor() {
        let mut c=p(Primitive::Cubic);
        c.move_node(1,Point::new(2.0,3.0)).unwrap();
        assert_eq!(c.nodes[0].position,Point::new(2.0,3.0));
        if let Curve::Cubic{control1,..}=c.segments[0].curve {
            assert_eq!(control1,Point::new(14.5,33.0));
        }else{panic!("Lost retained cubic");}
    }
    #[test]
    fn arc_endpoint_refit_remains_circular_and_undoable() {
        let mut a=p(Primitive::Arc);
        a.move_node(1,Point::new(2.0,3.0)).unwrap();
        assert_eq!(a.nodes[0].position,Point::new(2.0,3.0));
        assert!(matches!(a.segments[0].curve,Curve::Arc{..}));
        a.validate().unwrap();
        let previous=a.clone();
        assert!(a.move_node(1,a.nodes[1].position).is_err());
        assert_eq!(a,previous);
    }
    #[test]
    fn split_line_and_rejoin_preserves_original_segment_id() {
        let mut a=p(Primitive::Line);
        let id=a.split_line_after(1).unwrap();
        assert_eq!(id,4);
        assert_eq!(a.segments.iter().map(|s|s.id).collect::<Vec<_>>(),vec![3,5]);
        assert_eq!(a.nodes[1].position,Point::new(25.0,0.0));
        a.remove_node(id).unwrap();
        assert_eq!(a.segments[0].id,3);
        assert_eq!(a.nodes.len(),2);
        assert_eq!(a.next_element_id,6);
    }
    #[test]
    fn removing_open_endpoints_does_not_underflow_node_index(){
        let mut path=p(Primitive::Line);
        let mid=path.split_line_after(1).unwrap();
        path.remove_node(1).unwrap();
        assert_eq!(path.nodes.len(),2);
        assert_eq!(path.nodes[0].id,mid);
        assert_eq!(path.segments.len(),1);
        path.validate().unwrap();
        let mut path=p(Primitive::Line);
        path.split_line_after(1).unwrap();
        path.remove_node(2).unwrap();
        assert_eq!(path.nodes.len(),2);
        path.validate().unwrap();
    }
    #[test]
    fn disallows_silent_split_or_deletion_of_curves() {
        let mut a=p(Primitive::Arc);
        assert!(a.split_line_after(1).is_err());
        let mut b=p(Primitive::Cubic);
        assert!(b.split_line_after(1).is_err());
        assert!(b.remove_node(1).is_err());
    }
    #[test]
    fn bad_duplicate_id_and_excessive_nodes_fail_closed() {
        let mut a=p(Primitive::Line);
        a.segments[0].id=1;
        assert!(a.validate().is_err());
        let mut a=p(Primitive::Line);
        a.nodes.extend((0..260).map(|j|PathNode{id:200+j,position:Point::new(j as f64,100.0)}));
        assert!(a.validate().is_err());
    }
}
