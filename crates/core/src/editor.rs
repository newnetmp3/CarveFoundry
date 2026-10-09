//! Validated undoable Rust design commands. Machine output is out of scope.
use crate::{geometry::Point, path::{AnalyticPath, Curve, PathSegment, Primitive}, project::{Contour, Fixture, Project, Stock}};

#[derive(Clone, Debug)]
pub enum Action {
    AddRectangle { name: String, origin: Point, width_mm: f64, height_mm: f64 },
    AddAnalytic { name: String, origin: Point, kind: Primitive, width_mm: f64, height_mm: f64 },
    MovePath { id: u64, origin: Point },
    MoveNode { path_id: u64, node_id: u64, position: Point },
    MoveControl { path_id: u64, segment_id: u64, handle: u8, position: Point },
    InsertNodeAfter { path_id: u64, node_id: u64 },
    RemoveNode { path_id: u64, node_id: u64 },
    SetPathClosed { id: u64, closed: bool },
    SetPathLocked { id: u64, locked: bool },
    RemovePath { id: u64 },
    Move { id: u64, origin: Point },
    Rename { id: u64, name: String },
    SetLocked { id: u64, locked: bool },
    Remove { id: u64 },
    ChangeStock(Stock),
    AddFixture(Fixture),
}
#[derive(Clone, Debug)]
pub struct Editor {
    pub project: Project,
    undo: Vec<Project>,
    redo: Vec<Project>,
    drag_before: Option<Project>,
}
impl Default for Editor {
    fn default() -> Self {Self::new(Project::default()).expect("valid default project")}
}
impl Editor {
    pub fn new(project: Project) -> Result<Self,String> {
        project.validate()?;
        Ok(Self {project,undo:vec![],redo:vec![],drag_before:None})
    }
    pub fn can_undo(&self) -> bool { !self.undo.is_empty() }
    pub fn can_redo(&self) -> bool { !self.redo.is_empty() }
    fn store(&mut self, before: Project) {
        self.undo.push(before);
        if self.undo.len()>64 { self.undo.remove(0); }
        self.redo.clear();
    }
    pub fn apply(&mut self, action: Action) -> Result<(),String> {
        if self.drag_before.is_some() {
            return Err("Finish the active drag before editing another object".into());
        }
        let mut next=self.project.clone();
        match action {
            Action::AddRectangle{name,origin,width_mm,height_mm} => {
                if !width_mm.is_finite() || !height_mm.is_finite()
                    || !(0.1..=10_000.).contains(&width_mm)
                    || !(0.1..=10_000.).contains(&height_mm) {
                    return Err("Rectangle dimensions must be 0.1–10,000 mm".into());
                }
                let id=next.next_id;
                next.next_id=next.next_id.checked_add(1).ok_or("Contour ID exhausted")?;
                next.contours.push(Contour {
                    id,name,visible:true,locked:false,origin,
                    vertices:vec![
                        Point::new(0.,0.),Point::new(width_mm,0.),
                        Point::new(width_mm,height_mm),Point::new(0.,height_mm),
                    ],
                });
            }
            Action::AddAnalytic{name,origin,kind,width_mm,height_mm} => {
                let id=next.next_id;
                let path=AnalyticPath::preset(id,name,origin,kind,width_mm,height_mm)?;
                next.next_id=next.next_id.checked_add(1).ok_or("Path ID exhausted")?;
                next.paths.push(path);
            }
            Action::MovePath{id,origin} => {
                let path=next.paths.iter_mut().find(|p|p.id==id)
                    .ok_or("Analytic path ID not found")?;
                if path.locked{return Err("Path is locked".into());}
                path.origin=origin;
            }
            Action::MoveNode{path_id,node_id,position} => {
                let path=next.paths.iter_mut().find(|p|p.id==path_id)
                    .ok_or("Analytic path ID not found")?;
                if path.locked {return Err("Path is locked".into());}
                path.move_node(node_id,position)?;
            }
            Action::MoveControl{path_id,segment_id,handle,position} => {
                let path=next.paths.iter_mut().find(|p|p.id==path_id)
                    .ok_or("Analytic path ID not found")?;
                if path.locked{return Err("Path is locked".into());}
                path.move_control(segment_id,handle,position)?;
            }
            Action::InsertNodeAfter{path_id,node_id} => {
                let path=next.paths.iter_mut().find(|p|p.id==path_id)
                    .ok_or("Analytic path ID not found")?;
                if path.locked{return Err("Path is locked".into());}
                path.split_line_after(node_id)?;
            }
            Action::RemoveNode{path_id,node_id} => {
                let path=next.paths.iter_mut().find(|p|p.id==path_id)
                    .ok_or("Analytic path ID not found")?;
                if path.locked{return Err("Path is locked".into());}
                path.remove_node(node_id)?;
            }
            Action::SetPathClosed{id,closed} => {
                let path=next.paths.iter_mut().find(|p|p.id==id)
                    .ok_or("Analytic path ID not found")?;
                if path.locked{return Err("Path is locked".into());}
                if path.closed!=closed {
                    if closed {
                        if path.nodes.len()<3{return Err("Closed path requires three nodes".into());}
                        let id=path.next_element_id;
                        path.next_element_id=id.checked_add(1).ok_or("Segment IDs exhausted")?;
                        path.segments.push(PathSegment{id,curve:Curve::Line});
                    } else {
                        path.segments.pop();
                    }
                    path.closed=closed;
                }
            }
            Action::SetPathLocked{id,locked} => {
                let path=next.paths.iter_mut().find(|p|p.id==id)
                    .ok_or("Analytic path ID not found")?;
                path.locked=locked;
            }
            Action::RemovePath{id} => {
                let path=next.paths.iter().find(|p|p.id==id)
                    .ok_or("Analytic path ID not found")?;
                if path.locked{return Err("Path is locked".into());}
                next.paths.retain(|p|p.id!=id);
            }
            Action::Move{id,origin} => {
                let item=next.contours.iter_mut().find(|p|p.id==id)
                    .ok_or("Contour ID not found")?;
                if item.locked {return Err("Contour is locked".into());}
                item.origin=origin;
            }
            Action::Rename{id,name} => {
                let item=next.contours.iter_mut().find(|p|p.id==id)
                    .ok_or("Contour ID not found")?;
                if item.locked {return Err("Contour is locked".into());}
                item.name=name;
            }
            Action::SetLocked{id,locked} => {
                let item=next.contours.iter_mut().find(|p|p.id==id)
                    .ok_or("Contour ID not found")?;
                item.locked=locked;
            }
            Action::Remove{id} => {
                let item=next.contours.iter().find(|p|p.id==id)
                    .ok_or("Contour ID not found")?;
                if item.locked {return Err("Contour is locked".into());}
                next.contours.retain(|p|p.id!=id);
            }
            Action::ChangeStock(stock) => next.stock=stock,
            Action::AddFixture(fixture) => next.fixtures.push(fixture),
        }
        next.validate()?;
        if next!=self.project {
            let before=std::mem::replace(&mut self.project,next);
            self.store(before);
        }
        Ok(())
    }
    pub fn start_drag(&mut self, id: u64) -> Result<Point,String> {
        if self.drag_before.is_some() {return Err("Drag already active".into());}
        let contour=self.project.contours.iter().find(|p|p.id==id)
            .ok_or("Contour ID not found")?;
        if contour.locked || !contour.visible {
            return Err("Cannot move a hidden or locked contour".into());
        }
        let origin=contour.origin;
        self.drag_before=Some(self.project.clone());
        Ok(origin)
    }
    pub fn preview_drag(&mut self,id:u64,origin:Point) -> Result<(),String> {
        let before=self.drag_before.as_ref().ok_or("Drag has not started")?;
        let original=before.contours.iter().find(|p|p.id==id)
            .ok_or("Dragged contour ID was removed")?;
        if original.locked {return Err("Dragged contour is locked".into());}
        let mut candidate=before.clone();
        candidate.contours.iter_mut().find(|p|p.id==id)
            .ok_or("Dragged contour missing")?.origin=origin;
        candidate.validate()?;
        self.project=candidate;
        Ok(())
    }
    pub fn start_path_drag(&mut self,id:u64)->Result<Point,String> {
        if self.drag_before.is_some(){return Err("Drag already active".into());}
        let path=self.project.paths.iter().find(|p|p.id==id)
            .ok_or("Analytic path ID not found")?;
        if path.locked || !path.visible {return Err("Cannot move a hidden or locked path".into());}
        let anchor=path.origin;
        self.drag_before=Some(self.project.clone());
        Ok(anchor)
    }
    pub fn preview_path_drag(&mut self,id:u64,origin:Point)->Result<(),String>{
        let baseline=self.drag_before.as_ref().ok_or("Drag not started")?;
        let path=baseline.paths.iter().find(|p|p.id==id)
            .ok_or("Analytic path ID not found")?;
        if path.locked{return Err("Path is locked".into());}
        let mut candidate=baseline.clone();
        candidate.paths.iter_mut().find(|p|p.id==id)
            .ok_or("Path disappeared")?.origin=origin;
        candidate.validate()?;
        self.project=candidate;
        Ok(())
    }
    pub fn start_node_drag(&mut self,path_id:u64,node_id:u64)->Result<Point,String>{
        if self.drag_before.is_some(){return Err("Drag already active".into());}
        let path=self.project.paths.iter().find(|p|p.id==path_id)
            .ok_or("Analytic path ID not found")?;
        if path.locked || !path.visible {return Err("Cannot edit hidden or locked path".into());}
        let node=path.nodes.iter().find(|n|n.id==node_id)
            .ok_or("Node ID not found")?;
        let pos=node.position;
        self.drag_before=Some(self.project.clone());
        Ok(pos)
    }
    pub fn preview_node_drag(&mut self,path_id:u64,node_id:u64,position:Point)
        -> Result<(),String> {
        let baseline=self.drag_before.as_ref().ok_or("Drag not started")?;
        let mut candidate=baseline.clone();
        let path=candidate.paths.iter_mut().find(|p|p.id==path_id)
            .ok_or("Analytic path ID not found")?;
        if path.locked{return Err("Path is locked".into());}
        path.move_node(node_id,position)?;
        candidate.validate()?;
        self.project=candidate;
        Ok(())
    }
    pub fn finish_drag(&mut self) {
        if let Some(before)=self.drag_before.take() && before!=self.project {
            self.store(before);
        }
    }
    pub fn cancel_drag(&mut self) {
        if let Some(before)=self.drag_before.take(){self.project=before;}
    }
    pub fn undo(&mut self) -> bool {
        if self.drag_before.is_some() {return false;}
        if let Some(prev)=self.undo.pop(){
            self.redo.push(std::mem::replace(&mut self.project,prev));
            return true;
        }
        false
    }
    pub fn redo(&mut self) -> bool {
        if self.drag_before.is_some() {return false;}
        if let Some(next)=self.redo.pop(){
            self.undo.push(std::mem::replace(&mut self.project,next));
            return true;
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn rect() -> Action {
        Action::AddRectangle{name:"Panel".into(),origin:Point::new(20.,30.),
            width_mm:50.,height_mm:20.}
    }


    #[test]
    fn analytic_creation_edit_and_undo_are_lossless() {
        let mut e=Editor::default();
        e.apply(Action::AddAnalytic {name:"Handle curve".into(),
            origin:Point::new(15.0,20.0),kind:Primitive::Cubic,
            width_mm:50.0,height_mm:20.0}).unwrap();
        let source=e.project.clone();
        let id=e.project.paths[0].id;
        let node=e.project.paths[0].nodes[0].id;
        e.apply(Action::MoveNode{path_id:id,node_id:node,
            position:Point::new(5.0,3.0)}).unwrap();
        assert_eq!(e.project.paths[0].nodes[0].position,Point::new(5.0,3.0));
        assert!(e.undo());
        assert_eq!(e.project,source);
        assert!(e.redo());
        let decoded=Project::decode(&e.project.encode().unwrap()).unwrap();
        assert_eq!(decoded,e.project);
        assert!(matches!(decoded.paths[0].segments[0].curve,Curve::Cubic{..}));
        assert_eq!(decoded.paths[0].nodes[0].id,node);
    }
    #[test]
    fn editing_arc_anchors_is_rejected_without_change() {
        let mut e=Editor::default();
        e.apply(Action::AddAnalytic{name:"Arch".into(),
            origin:Point::new(0.0,0.0),kind:Primitive::Arc,
            width_mm:50.0,height_mm:20.0}).unwrap();
        let before=e.project.clone();
        assert!(e.apply(Action::MoveNode{path_id:1,node_id:1,
            position:Point::new(2.0,2.0)}).is_err());
        assert_eq!(e.project,before);
        let node=e.start_node_drag(1,1).unwrap();
        assert!(e.preview_node_drag(1,1,node.offset(2.0,1.0)).is_err());
        e.cancel_drag();
        assert_eq!(e.project,before);
    }
    #[test]
    fn split_delete_and_close_validate_as_one_transaction_each(){
        let mut e=Editor::default();
        e.apply(Action::AddAnalytic{name:"Outline".into(),
            origin:Point::new(0.0,0.0),kind:Primitive::Line,
            width_mm:50.0,height_mm:10.0}).unwrap();
        e.apply(Action::InsertNodeAfter{path_id:1,node_id:1}).unwrap();
        assert_eq!(e.project.paths[0].nodes.len(),3);
        // Three collinear points cannot form a valid closed area.
        assert!(e.apply(Action::SetPathClosed{id:1,closed:true}).is_err());
        assert!(!e.project.paths[0].closed);
        e.apply(Action::MoveNode{path_id:1,node_id:4,
            position:Point::new(25.0,12.0)}).unwrap();
        e.apply(Action::SetPathClosed{id:1,closed:true}).unwrap();
        assert_eq!(e.project.paths[0].segments.len(),3);
        assert!(e.undo());
        assert!(!e.project.paths[0].closed);
        e.apply(Action::RemoveNode{path_id:1,node_id:4}).unwrap();
        assert_eq!(e.project.paths[0].nodes.len(),2);
    }
    #[test]
    fn stable_undoable_analytic_drag_and_locking(){
        let mut e=Editor::default();
        e.apply(Action::AddAnalytic{name:"Edge".into(),
            origin:Point::new(5.0,5.0),kind:Primitive::Line,
            width_mm:40.0,height_mm:10.0}).unwrap();
        let before=e.project.clone();
        let start=e.start_path_drag(1).unwrap();
        e.preview_path_drag(1,start.offset(1.0,1.0)).unwrap();
        e.preview_path_drag(1,start.offset(5.0,2.0)).unwrap();
        e.finish_drag();
        assert_eq!(e.project.paths[0].origin,start.offset(5.0,2.0));
        assert!(e.undo());
        assert_eq!(e.project,before);
        e.apply(Action::SetPathLocked{id:1,locked:true}).unwrap();
        assert!(e.apply(Action::RemovePath{id:1}).is_err());
        assert!(e.start_path_drag(1).is_err());
    }

    #[test]
    fn edit_history_is_undoable_with_stable_ids(){
        let mut e=Editor::default();
        e.apply(rect()).unwrap();
        assert_eq!(e.project.contours[0].id,1);
        e.apply(Action::Move{id:1,origin:Point::new(21.,32.)}).unwrap();
        assert_eq!(e.project.contours[0].origin,Point::new(21.,32.));
        assert!(e.undo());
        assert_eq!(e.project.contours[0].origin,Point::new(20.,30.));
        assert!(e.redo());
        assert_eq!(e.project.contours[0].id,1);
        assert_eq!(Project::decode(&e.project.encode().unwrap()).unwrap(),e.project);
    }
    #[test]
    fn locked_rejection_never_mutates_or_pushes_history() {
        let mut e=Editor::default();
        e.apply(rect()).unwrap();
        e.apply(Action::SetLocked{id:1,locked:true}).unwrap();
        let before=e.project.clone();
        assert!(e.apply(Action::Move{id:1,origin:Point::new(9.,9.)}).is_err());
        assert!(e.apply(Action::Remove{id:1}).is_err());
        assert!(e.start_drag(1).is_err());
        assert_eq!(e.project,before);
        assert!(e.undo());
        assert!(!e.project.contours[0].locked);
    }
    #[test]
    fn drag_undo_is_one_transaction_not_one_per_frame(){
        let mut e=Editor::default();
        e.apply(rect()).unwrap();
        let before=e.project.clone();
        let start=e.start_drag(1).unwrap();
        e.preview_drag(1,start.offset(0.1,0.2)).unwrap();
        e.preview_drag(1,start.offset(4.,3.)).unwrap();
        assert!(e.preview_drag(1,Point::new(f64::NAN,0.)).is_err());
        e.finish_drag();
        assert_eq!(e.project.contours[0].origin,start.offset(4.,3.));
        assert!(e.undo());
        assert_eq!(e.project,before);
    }
    #[test]
    fn cancel_drag_restores_source_and_invalid_rejects_atomically(){
        let mut e=Editor::default();
        e.apply(rect()).unwrap();
        let before=e.project.clone();
        e.start_drag(1).unwrap();
        e.preview_drag(1,Point::new(42.,42.)).unwrap();
        e.cancel_drag();
        assert_eq!(e.project,before);
        assert!(e.apply(Action::AddRectangle{name:"bad".into(),
            origin:Point::new(0.,0.),width_mm:f64::INFINITY,
            height_mm:1.}).is_err());
        assert_eq!(e.project,before);
    }
}
