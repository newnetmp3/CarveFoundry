//! Source-exact, read-only classification of nested 2D CAD boundaries.
//! No machine region, fill, cutter compensation, or G-code is generated.
//! Only proven-simple, mutually disjoint closed lines / circular arcs.
use std::collections::HashSet;
use crate::{AnalyticPath,Curve};
use crate::intersections::{
    validate_simple_analytic_chain,
    require_disjoint_closed_boundaries,
    closed_line_arc_contains,
};

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
    for i in 0..n {
        for j in i+1..n {
            if within[i][j] && within[j][i]{
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
