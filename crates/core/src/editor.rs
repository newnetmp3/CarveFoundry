//! Validated undoable Rust design commands. Machine output is out of scope.
use crate::{geometry::Point, project::{Contour, Fixture, Project, Stock}};

#[derive(Clone, Debug)]
pub enum Action {
    AddRectangle { name: String, origin: Point, width_mm: f64, height_mm: f64 },
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
    pub fn finish_drag(&mut self) {
        if let Some(before)=self.drag_before.take() {
            if before!=self.project {self.store(before);}
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
