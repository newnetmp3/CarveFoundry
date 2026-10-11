//! Exact source-line splitting and directed boundary stitching for CAD
//! booleans of transverse, non-coincident straight-line compound regions.
//! This is NOT curve tessellation and NEVER emits CAM/G-code.
use crate::{
    geometry::{Point,signed_area},
    path::{AnalyticPath,Curve,PathNode,PathSegment},
    compound::{analyze_compound_paths,CompoundRole},
    intersections::{closed_line_arc_contains,closed_line_arc_on_boundary},
    Project,
};
use crate::region_booleans::RegionBoolean;
use std::collections::HashMap;

const VERTEX_TOL:f64=1e-7;
const PARAM_TOL:f64=1e-8;
const MAX_EDGES:usize=1024;
const MAX_CROSSINGS:usize=256;
const MAX_RESULT_EDGES:usize=2048;
fn sub(a:Point,b:Point)->Point{Point::new(a.x-b.x,a.y-b.y)}
fn cross(a:Point,b:Point)->f64{a.x*b.y-a.y*b.x}
fn dot(a:Point,b:Point)->f64{a.x*b.x+a.y*b.y}
fn len(a:Point)->f64{a.x.hypot(a.y)}
fn distance(a:Point,b:Point)->f64{len(sub(a,b))}
fn lerp(a:Point,b:Point,t:f64)->Point{
    Point::new(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t)
}
#[derive(Clone,Copy)]
struct Edge{a:Point,b:Point,material_left:bool,side:usize}
struct Fragment {a:Point,b:Point}
fn source_edges(paths:&[AnalyticPath],side:usize)
    ->Result<Vec<Edge>,String>{
    let roles=analyze_compound_paths(paths)?;
    let role_by_id=roles.iter().map(|r|(r.path_id,r.role))
        .collect::<HashMap<_,_>>();
    let mut edges=Vec::new();
    for path in paths{
        if path.segments.iter().any(|s|!matches!(s.curve,Curve::Line)){
            return Err("Transverse Boolean splitting currently requires straight-line source loops".into());
        }
        let ccw=signed_area(&path.nodes.iter().map(|n|n.position)
            .collect::<Vec<_>>())>0.0;
        let outer=role_by_id.get(&path.id)==Some(&CompoundRole::Outline);
        let material_left=ccw==outer;
        let n=path.nodes.len();
        for i in 0..n{
            let a=path.nodes[i].position.offset(path.origin.x,path.origin.y);
            let b=path.nodes[(i+1)%n].position.offset(path.origin.x,path.origin.y);
            edges.push(Edge{a,b,material_left,side});
        }
    }
    Ok(edges)
}
fn region_contains(paths:&[AnalyticPath],point:Point)->Result<bool,String>{
    let mut inside=false;
    for path in paths{
        if closed_line_arc_on_boundary(path,point)?{
            return Err(format!(
                "Boolean fragment classification is on/too close to source vector #{}",
                path.id
            ));
        }
        if closed_line_arc_contains(path,point)?{inside=!inside;}
    }
    Ok(inside)
}
fn contact_parameters(first:Edge,second:Edge)
    ->Result<Option<(f64,f64,Point)>,String>{
    let u=sub(first.b,first.a);
    let v=sub(second.b,second.a);
    let lu=len(u);
    let lv=len(v);
    let w=sub(second.a,first.a);
    let d=cross(u,v);
    if d.abs()<1e-11*lu*lv {
        // Parallel supports are fine when strictly distinct. Shared
        // collinear points/intervals are not: no arbitrary ownership of
        // their boundary or zero-width Boolean regions.
        if cross(w,u).abs()<VERTEX_TOL*lu{
            let t0=dot(sub(second.a,first.a),u)/(lu*lu);
            let t1=dot(sub(second.b,first.a),u)/(lu*lu);
            if t0.min(t1).max(0.0)<=t0.max(t1).min(1.0)+PARAM_TOL{
                return Err("Transverse Boolean refuses coincident/touching straight edges".into());
            }
        }
        return Ok(None);
    }
    let t=cross(w,v)/d;
    let s=cross(w,u)/d;
    if t < -PARAM_TOL||t > 1.0+PARAM_TOL
        ||s < -PARAM_TOL||s > 1.0+PARAM_TOL{
        return Ok(None);
    }
    if t<=PARAM_TOL||t>=1.0-PARAM_TOL
        ||s<=PARAM_TOL||s>=1.0-PARAM_TOL {
        return Err("Transverse Boolean refuses touching vertices or T-junction boundaries".into());
    }
    let p=lerp(first.a,first.b,t);
    if !p.finite(){return Err("Boolean split would exceed finite design bounds".into());}
    Ok(Some((t,s,p)))
}
fn collect_splits(edges:&[Edge],left_count:usize)
    ->Result<(Vec<Vec<f64>>,usize),String>{
    let mut parameters=vec![vec![0.0,1.0];edges.len()];
    let mut n=0usize;
    for i in 0..left_count{
        for j in left_count..edges.len(){
            if let Some((t,s,_))=contact_parameters(edges[i],edges[j])?{
                parameters[i].push(t);
                parameters[j].push(s);
                n+=1;
                if n>MAX_CROSSINGS{
                    return Err("Boolean source intersections exceed 256 exact crossings".into());
                }
            }
        }
    }
    for positions in &mut parameters{
        positions.sort_by(f64::total_cmp);
        for window in positions.windows(2){
            if window[1]-window[0]<PARAM_TOL{
                return Err("Boolean intersection points are too close to prove unique topology".into());
            }
        }
    }
    Ok((parameters,n))
}
fn classify_fragments(edges:&[Edge],splits:&[Vec<f64>],
    left:&[AnalyticPath],right:&[AnalyticPath],
    op:RegionBoolean)->Result<Vec<Fragment>,String>{
    let mut output=Vec::new();
    for (edge,values) in edges.iter().zip(splits){
        // Exact midpoint on the retained straight source edge.
        // Because every crossing was split, it is strictly outside
        // all OTHER-operand boundaries (or the query fails closed).
        for params in values.windows(2){
            let a=lerp(edge.a,edge.b,params[0]);
            let b=lerp(edge.a,edge.b,params[1]);
            let point=lerp(a,b,0.5);
            let (result_left,result_right)=if edge.side==0{
                let material=region_contains(right,point)?;
                (op.material(edge.material_left,material),
                 op.material(!edge.material_left,material))
            }else{
                let material=region_contains(left,point)?;
                (op.material(material,edge.material_left),
                 op.material(material,!edge.material_left))
            };
            if result_left!=result_right{
                // All retained fragments face with result material
                // on their LEFT. This makes stitching deterministic
                // even for CW source loops and hole rings.
                let oriented=if result_left{
                    Fragment{a,b}
                }else{
                    Fragment{a:b,b:a}
                };
                if distance(oriented.a,oriented.b)<VERTEX_TOL{
                    return Err("Boolean result would create a zero-length edge".into());
                }
                output.push(oriented);
                if output.len()>MAX_RESULT_EDGES{
                    return Err("Boolean result exceeds 2048 split edges".into());
                }
            }
        }
    }
    Ok(output)
}
fn link_vertex(vertices:&mut Vec<Point>,p:Point)->Result<usize,String>{
    for (i,v) in vertices.iter().enumerate(){
        if distance(*v,p)<VERTEX_TOL{
            // Canonicalize computed crossings but reject visibly
            // distinct nearby coordinates which risk topology change.
            return Ok(i);
        }
    }
    vertices.push(p);
    Ok(vertices.len()-1)
}
fn stitch(fragments:&[Fragment])->Result<Vec<AnalyticPath>,String>{
    if fragments.is_empty(){
        return Err("Exact Boolean result is empty; no editable boundaries generated".into());
    }
    let mut vertices=Vec::<Point>::new();
    let mut indexed=Vec::with_capacity(fragments.len());
    for f in fragments{
        let a=link_vertex(&mut vertices,f.a)?;
        let b=link_vertex(&mut vertices,f.b)?;
        if a==b{return Err("Boolean fragment collapses at a shared vertex".into());}
        indexed.push((a,b));
    }
    let mut outgoing=vec![None::<usize>;vertices.len()];
    let mut incoming=vec![0usize;vertices.len()];
    for (i,(a,b)) in indexed.iter().copied().enumerate(){
        if outgoing[a].replace(i).is_some(){
            return Err("Boolean result has branching or overlapping outgoing edges".into());
        }
        incoming[b]+=1;
        if incoming[b]>1{
            return Err("Boolean result has multiple incoming edges at one vertex".into());
        }
    }
    if incoming.iter().any(|degree|*degree!=1)
        ||outgoing.iter().any(Option::is_none){
        return Err("Boolean fragments cannot form unique closed boundaries".into());
    }
    let mut used=vec![false;indexed.len()];
    let mut paths=Vec::new();
    for start in 0..indexed.len(){
        if used[start]{continue;}
        let mut index=start;
        let mut points=Vec::new();
        loop{
            if used[index]{
                if index!=start{
                    return Err("Boolean split reconstruction would revisit another loop".into());
                }
                break;
            }
            used[index]=true;
            let (a,b)=indexed[index];
            points.push(vertices[a]);
            if points.len()>256{
                return Err("Boolean output loop exceeds the 256-node native design bound".into());
            }
            let next=outgoing[b].ok_or("Boolean boundary is not closed")?;
            index=next;
        }
        if points.len()<3{
            return Err("Boolean output cannot represent a degenerate two-edge loop".into());
        }
        let n=points.len();
        // World-space exact source-line intersection vertices become
        // new independent native line nodes; no arcs or cubic samples.
        let path=AnalyticPath{
            id:paths.len() as u64+1,
            name:format!("Boolean exact loop {}",paths.len()+1),
            origin:Point::new(0.0,0.0),
            visible:true,locked:false,closed:true,
            nodes:points.into_iter().enumerate().map(|(i,position)|
                PathNode{id:i as u64+1,position}).collect(),
            segments:(0..n).map(|i|PathSegment{
                id:n as u64+i as u64+1,curve:Curve::Line,
            }).collect(),
            next_element_id:2*n as u64+1,
        };
        path.validate()?;
        paths.push(path);
    }
    analyze_compound_paths(&paths).map_err(|problem|
        format!("Rebuilt Boolean source loops are not valid: {problem}"))?;
    Ok(paths)
}
/// Reconstruct cut-and-joined CLOSED line contours for cases where
/// different operands have strict transverse interior/interior hits.
/// All intersections, contacts and topology decisions are analytic.
pub(crate) fn split_transverse_boolean(
    project:&Project,left:&[AnalyticPath],right:&[AnalyticPath],
    op:RegionBoolean,
)->Result<Vec<AnalyticPath>,String>{
    let _=project;
    let mut edges=source_edges(left,0)?;
    let left_count=edges.len();
    edges.extend(source_edges(right,1)?);
    if edges.len()>MAX_EDGES{
        return Err("Transverse Boolean source exceeds 1024 straight edges".into());
    }
    let (parameters,crossings)=collect_splits(&edges,left_count)?;
    if crossings==0{
        return Err("Transverse Boolean has no strict crossing; coincident/tangent boundaries are unsupported".into());
    }
    let fragments=classify_fragments(&edges,&parameters,left,right,op)?;
    stitch(&fragments)
}
