//! Source-exact, read-only classification of nested 2D CAD boundaries.
//! No machine region, fill, cutter compensation, or G-code is generated.
//! Only proven-simple, mutually disjoint closed lines / circular arcs.
use std::collections::HashSet;
use crate::{AnalyticPath,Curve,Point,Project};
use serde::{Deserialize,Serialize};
use crate::intersections::{
    validate_simple_analytic_chain,
    require_disjoint_closed_boundaries,
    closed_line_arc_contains,
};

/// Durable, independent source-loop membership. This is a CAD Boolean
/// expression over non-touching closed paths, never a flattened replacement.
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CompoundRegion{
    pub id:u64,
    pub name:String,
    pub path_ids:Vec<u64>,
}
impl Project {
    /// Validate persisted Boolean parity membership against CURRENT sources.
    /// Called by every atomic edit and drag-preview commit via Project::validate.
    pub(crate) fn validate_compound_regions(&self)->Result<(),String>{
        if self.compound_regions.len()>64{
            return Err("Compound CAD exceeds 64 saved regions".into());
        }
        let mut identities=self.paths.iter().map(|p|p.id)
            .chain(self.contours.iter().map(|p|p.id))
            .chain(self.text_runs.iter().map(|x|x.id))
            .chain(self.layers.iter().map(|x|x.id))
            .chain(self.groups.iter().map(|x|x.id))
            .collect::<HashSet<_>>();
        let mut used_sources=HashSet::new();
        for region in &self.compound_regions{
            if region.id==0||region.id>=self.next_id
                || !identities.insert(region.id)
                || !crate::organization::valid_name(&region.name)
                || !(2..=32).contains(&region.path_ids.len()){
                return Err("Invalid compound region identity, name or member count".into());
            }
            let mut sources=Vec::with_capacity(region.path_ids.len());
            for id in &region.path_ids{
                if !used_sources.insert(*id){
                    return Err("Compound source vector belongs to multiple saved regions or is repeated".into());
                }
                let source=self.paths.iter().find(|p|p.id==*id)
                    .ok_or("Compound region references a missing analytic source vector")?;
                sources.push(source.clone());
            }
            analyze_compound_paths(&sources).map_err(|problem|
                format!("Compound region #{} would become invalid: {problem}",region.id))?;
        }
        Ok(())
    }
    /// Exact point-membership for a saved even/odd Boolean region.
    /// Returns an error on the boundary: its meaning is not an interior
    /// clearance claim. Independent outer paths UNION, nested hole
    /// paths SUBTRACT, and nested islands UNION by parity.
    pub fn compound_material_at(&self,region_id:u64,point:Point)
        ->Result<bool,String>{
        self.validate()?;
        if !point.finite(){
            return Err("Compound CAD query must be a finite XY design point".into());
        }
        let region=self.compound_regions.iter().find(|r|r.id==region_id)
            .ok_or("Unknown saved compound region")?;
        let mut inside=false;
        for id in &region.path_ids{
            let path=self.paths.iter().find(|p|p.id==*id)
                .ok_or("Compound source path missing")?;
            if crate::intersections::closed_line_arc_on_boundary(path,point)?{
                return Err("Compound CAD point lies on a boundary; interior/exterior is ambiguous".into());
            }
            if closed_line_arc_contains(path,point)?{
                inside=!inside;
            }
        }
        Ok(inside)
    }
}

/// Even/odd region role, independent of source path winding.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum CompoundRole { Outline, Hole }
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct CompoundLoop {
    pub path_id:u64,
    pub parent_path_id:Option<u64>,
    pub depth:usize,
    pub role:CompoundRole,
}
/// Return a deterministic topological hierarchy in the same input order.
/// Outer regions are depth 0, holes depth 1, islands depth 2, etc.
/// The existing editable paths are NEVER changed or relinked; the
/// hierarchy is a verified read-only interpretation of selected loops.
pub fn analyze_compound_paths(paths:&[AnalyticPath])
    ->Result<Vec<CompoundLoop>,String>{
    if paths.is_empty()||paths.len()>32{
        return Err("Compound analysis requires 1–32 selected closed vectors".into());
    }
    let mut ids=HashSet::new();
    let mut checked_pairs=0usize;
    for path in paths{
        if !ids.insert(path.id){
            return Err("Compound analysis has duplicate path IDs".into());
        }
        if !path.closed{
            return Err(format!("Vector #{} is open; select only closed loops",path.id));
        }
        if path.segments.iter().any(|s|matches!(s.curve,Curve::Cubic{..})){
            return Err(format!(
                "Vector #{} uses cubic Béziers; compound containment is exact only for lines/circular arcs",
                path.id
            ));
        }
        validate_simple_analytic_chain(path)?;
    }
    let n=paths.len();
    for i in 0..n{
        for j in i+1..n{
            let pair_cost=paths[i].segments.len()
                .checked_mul(paths[j].segments.len())
                .ok_or("Compound edge pair count overflow")?;
            checked_pairs=checked_pairs.checked_add(pair_cost)
                .ok_or("Compound edge pair budget overflow")?;
            if checked_pairs>150_000{
                return Err("Compound contour scan exceeds 150,000 exact edge pairs".into());
            }
            require_disjoint_closed_boundaries(&paths[i],&paths[j])?;
        }
    }
    let mut within=vec![vec![false;n];n];
    for i in 0..n{
        let source=&paths[i];
        // One proved-off-boundary point suffices for any two simple
        // contours that neither cross nor touch. Never use a raster
        // centroid (which can lie OUTSIDE a concave source path).
        let first=source.nodes[0].position.offset(source.origin.x,source.origin.y);
        for j in 0..n{
            if i!=j{
                within[i][j]=closed_line_arc_contains(&paths[j],first)?;
            }
        }
    }
    for (i,row) in within.iter().enumerate(){
        for (j,other_row) in within.iter().enumerate().skip(i+1){
            if row[j] && other_row[i]{
                return Err("Compound nesting is contradictory; ambiguous containment refused".into());
            }
        }
    }
    let depth=(0..n).map(|i|within[i].iter().filter(|b|**b).count())
        .collect::<Vec<_>>();
    let mut result=Vec::with_capacity(n);
    for i in 0..n{
        let containers=(0..n).filter(|j|within[i][*j])
            .collect::<Vec<_>>();
        // Nested boundaries form a strict chain of containers. Enforce
        // this even when numerical edge cases cause an inconsistent
        // inside/outside classification.
        for (k,&a) in containers.iter().enumerate(){
            for &b in containers.iter().skip(k+1){
                if !within[a][b]&&!within[b][a]{
                    return Err("Compound containment is not a provable nested hierarchy".into());
                }
            }
        }
        let parent=containers.into_iter().max_by_key(|j|depth[*j]);
        result.push(CompoundLoop{
            path_id:paths[i].id,
            parent_path_id:parent.map(|j|paths[j].id),
            depth:depth[i],
            role:if depth[i].is_multiple_of(2){
                CompoundRole::Outline
            }else{
                CompoundRole::Hole
            },
        });
    }
    Ok(result)
}
