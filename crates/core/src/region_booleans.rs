//! Source-preserving Boolean CAD boundaries for provably disjoint/nested loops.
//! Never approximate true arcs, intersect crossing edges, or generate machine NC.
use crate::{AnalyticPath,Point,Project};
use crate::compound::analyze_compound_paths;
use crate::intersections::closed_line_arc_contains;

/// Boolean operation on the exact even/odd material of two saved regions.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum RegionBoolean { Union, Intersection, Difference }
impl RegionBoolean {
    fn material(self,a:bool,b:bool)->bool{
        match self{
            Self::Union=>a||b,
            Self::Intersection=>a&&b,
            Self::Difference=>a&&!b,
        }
    }
    pub fn title(self)->&'static str{
        match self{
            Self::Union=>"Union",
            Self::Intersection=>"Intersection",
            Self::Difference=>"A minus B",
        }
    }
}
fn contains(project:&Project,ids:&[u64],point:Point)->Result<bool,String>{
    let mut inside=false;
    for id in ids{
        let path=project.paths.iter().find(|p|p.id==*id)
            .ok_or("Saved Boolean region source path is missing")?;
        if closed_line_arc_contains(path,point)?{
            inside=!inside;
        }
    }
    Ok(inside)
}

/// Return retained source curves representing EXACT output boundaries.
/// Supports any union/intersection/difference for saved line/true-arc
/// regions whose combined input boundaries are non-touching and do not
/// cross. Every kept source loop is a complete, unchanged analytic path.
/// Intersecting/tangent/coincident inputs reject; there is no approximate
/// reconstruction of partial edge sweeps.
pub fn boolean_region_boundaries(
    project:&Project,left_region_id:u64,right_region_id:u64,
    operation:RegionBoolean,
)->Result<Vec<AnalyticPath>,String>{
    project.validate()?;
    if left_region_id==right_region_id{
        return Err("Select two different saved CAD regions for Boolean operations".into());
    }
    let left=project.compound_regions.iter().find(|r|r.id==left_region_id)
        .ok_or("First saved CAD region does not exist")?;
    let right=project.compound_regions.iter().find(|r|r.id==right_region_id)
        .ok_or("Second saved CAD region does not exist")?;
    let count=left.path_ids.len()+right.path_ids.len();
    if count>32{
        return Err("Exact Boolean requires no more than 32 total input source loops".into());
    }
    let all=left.path_ids.iter().chain(&right.path_ids)
        .map(|id|project.paths.iter().find(|p|p.id==*id)
            .ok_or("Boolean operand source is missing")
            .cloned())
        .collect::<Result<Vec<_>,_>>()?;
    // This is the critical safety condition: every source boundary
    // must be simple and every pair of INPUT boundaries disjoint.
    // The source-analytic classifier refuses ANY crossing, shared
    // point or coincident edge; it does not use display sampling.
    analyze_compound_paths(&all).map_err(|problem|
        format!("Boolean source boundaries cross/touch or cannot be proved disjoint: {problem}"))?;
    let mut selected=Vec::new();
    for source in &all[..left.path_ids.len()]{
        let point=source.nodes[0].position
            .offset(source.origin.x,source.origin.y);
        let b=contains(project,&right.path_ids,point)?;
        // Toggling the left material across this exact original edge
        // changes the result only when Boolean(0,b) != Boolean(1,b).
        if operation.material(false,b)!=operation.material(true,b){
            selected.push(source.clone());
        }
    }
    for source in &all[left.path_ids.len()..]{
        let point=source.nodes[0].position
            .offset(source.origin.x,source.origin.y);
        let a=contains(project,&left.path_ids,point)?;
        if operation.material(a,false)!=operation.material(a,true){
            selected.push(source.clone());
        }
    }
    if selected.is_empty(){
        return Err("Exact Boolean result is empty; no editable boundaries generated".into());
    }
    // An output set of retained complete simple loops must itself be
    // non-touching and have a strict, reconstructible hierarchy.
    analyze_compound_paths(&selected)?;
    Ok(selected)
}
