//! Persistent, flat CAD layers and vector groups.
//! These are non-geometric memberships; no curves are flattened or regenerated.
use serde::{Deserialize,Serialize};
use std::collections::HashSet;
use crate::project::Project;

#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DesignLayer {
    pub id:u64,
    pub name:String,
    pub visible:bool,
    pub locked:bool,
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LayerMember {
    pub vector_id:u64,
    pub layer_id:u64,
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VectorGroup {
    pub id:u64,
    pub name:String,
    pub visible:bool,
    pub locked:bool,
    pub members:Vec<u64>,
}
pub fn valid_name(name:&str)->bool{
    !name.trim().is_empty() && name.len()<=128 && !name.chars().any(char::is_control)
}
impl Project {
    /// Vector membership is optional: unassigned vectors live on the
    /// always-visible, always-editable virtual Base layer (ID zero).
    pub fn layer_for(&self,id:u64)->u64{
        self.layer_members.iter().find(|m|m.vector_id==id)
            .map_or(0,|m|m.layer_id)
    }
    pub fn group_for(&self,id:u64)->Option<&VectorGroup>{
        self.groups.iter().find(|g|g.members.contains(&id))
    }
    pub fn effective_visible(&self,id:u64)->bool{
        let object=self.paths.iter().find(|p|p.id==id)
            .map(|p|p.visible)
            .or_else(||self.contours.iter().find(|p|p.id==id).map(|p|p.visible))
            .unwrap_or(false);
        let layer=self.layer_for(id);
        object &&
            (layer==0 || self.layers.iter().any(|l|l.id==layer && l.visible)) &&
            self.group_for(id).is_none_or(|g|g.visible)
    }
    pub fn effective_locked(&self,id:u64)->bool{
        self.paths.iter().find(|p|p.id==id)
            .is_some_and(|p|p.locked)
            || self.contours.iter().find(|p|p.id==id)
                .is_some_and(|p|p.locked)
            || self.layers.iter().any(|l|l.id==self.layer_for(id)&&l.locked)
            || self.group_for(id).is_some_and(|g|g.locked)
    }
    pub fn editable_vector(&self,id:u64)->bool{
        self.effective_visible(id) && !self.effective_locked(id)
    }
    /// Expand group membership in Objects mode, never Node edit.
    /// At most one group owns each vector; groups cannot recursively nest.
    pub fn expand_groups(&self,ids:impl IntoIterator<Item=u64>)->Vec<u64>{
        let mut result=HashSet::new();
        for id in ids {
            if let Some(g)=self.group_for(id){
                for member in &g.members{result.insert(*member);}
            }else{result.insert(id);}
        }
        let mut sorted=result.into_iter().collect::<Vec<_>>();
        sorted.sort_unstable();
        sorted
    }
    pub(crate) fn validate_organization(&self)->Result<(),String>{
        if self.layers.len()>64||self.groups.len()>256||self.layer_members.len()>512{
            return Err("Layer or group count exceeds design limits".into());
        }
        let vectors=self.paths.iter().map(|v|v.id)
            .chain(self.contours.iter().map(|v|v.id))
            .collect::<HashSet<_>>();
        let mut ids=self.paths.iter().map(|p|p.id)
            .chain(self.contours.iter().map(|p|p.id))
            .chain(self.text_runs.iter().map(|v|v.id))
            .collect::<HashSet<_>>();
        let mut members=HashSet::new();
        for layer in &self.layers {
            if layer.id==0||layer.id>=self.next_id
                || !ids.insert(layer.id)||!valid_name(&layer.name){
                return Err("Invalid or duplicate design layer identity".into());
            }
        }
        let mut assigned=HashSet::new();
        for link in &self.layer_members {
            if !vectors.contains(&link.vector_id)
                || !assigned.insert(link.vector_id)
                || !self.layers.iter().any(|l|l.id==link.layer_id){
                return Err("Layer assignment targets an unknown or duplicate vector/layer".into());
            }
        }
        for group in &self.groups{
            if group.id==0||group.id>=self.next_id||!ids.insert(group.id)
                || !valid_name(&group.name)
                || !(2..=512).contains(&group.members.len()){
                return Err("Invalid or duplicate vector group".into());
            }
            for id in &group.members{
                if !vectors.contains(id)||!members.insert(*id){
                    return Err("Group references missing or multiply owned vectors".into());
                }
            }
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn old_projects_default_to_visible_unassigned_vectors(){
        let p=Project::default();
        assert_eq!(p.layer_for(1),0);
        assert!(p.groups.is_empty()&&p.layers.is_empty());
        p.validate().unwrap();
    }
}
