//! Validated undoable Rust design commands. Machine output is out of scope.
use std::collections::HashSet;
use crate::arrange::{Arrangement,arrangement_offsets};
use crate::{geometry::Point, path::{AnalyticPath, Curve, PathSegment, Primitive}, project::{Contour, Fixture, Project, Stock}, shapes::{create_shape,polyline,ShapeKind}};

#[derive(Clone, Debug)]
pub enum Action {
    AddRectangle { name: String, origin: Point, width_mm: f64, height_mm: f64 },
    AddShape {kind:ShapeKind,name:String,origin:Point,width_mm:f64,height_mm:f64},
    RenamePath {id:u64,name:String},
    RenameProject {name:String},
    AddPolyline {name:String,points:Vec<Point>,closed:bool},
    /// Atomic SVG vector import: assign fresh project-wide identities.
    ImportPaths {paths:Vec<AnalyticPath>},
    /// Insert or replace an editable text source and its vector contours atomically.
    SetText {id:Option<u64>,spec:crate::text::TextSpec,paths:Vec<AnalyticPath>},
    ConvertContour {id:u64},
    Duplicate {id:u64},
    DuplicateMany {ids:Vec<u64>},
    RemoveMany {ids:Vec<u64>},
    MoveMany {ids:Vec<u64>,delta:Point},
    Arrange {ids:Vec<u64>,mode:Arrangement},
    Flip {id:u64,horizontal:bool},
    RotateQuarter {id:u64,clockwise:bool},
    Center {id:u64,horizontal:bool,vertical:bool},
    SetVisible {id:u64,visible:bool},

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
            Action::RenameProject{name}=>{
                next.name=name;
            }
            Action::RenamePath{id,name}=>{
                let path=next.paths.iter_mut().find(|p|p.id==id)
                    .ok_or("Path ID not found")?;
                if path.locked{return Err("Path is locked".into());}
                path.name=name;
            }
            Action::AddShape{kind,name,origin,width_mm,height_mm}=>{
                let id=next.next_id;
                let path=create_shape(id,name,origin,kind,width_mm,height_mm)?;
                next.next_id=id.checked_add(1).ok_or("Shape ID exhausted")?;
                next.paths.push(path);
            }
            Action::AddPolyline{name,points,closed}=>{
                let id=next.next_id;
                let path=polyline(id,name,Point::new(0.0,0.0),points,closed)?;
                next.next_id=id.checked_add(1).ok_or("Path ID exhausted")?;
                next.paths.push(path);
            }
            Action::ImportPaths{paths}=>{
                if paths.is_empty() || paths.len()>512{
                    return Err("SVG import must contain 1 to 512 paths".into());
                }
                for mut path in paths {
                    path.validate()?;
                    path.id=next.next_id;
                    next.next_id=next.next_id.checked_add(1)
                        .ok_or("SVG imported vector identities exhausted")?;
                    next.paths.push(path);
                }
            }
            Action::SetText{id,spec,paths}=>{
                spec.validate()?;
                if paths.is_empty()||paths.len()>512{
                    return Err("Text requires 1–512 retained outline contours".into());
                }
                for p in &paths{p.validate()?;}
                let label_id=if let Some(id)=id {
                    let label=next.text_runs.iter().find(|run|run.id==id)
                        .ok_or("Editable text source not found")?;
                    if label.outline_ids.iter().any(|old|
                        next.paths.iter().find(|p|p.id==*old).is_none_or(|p|p.locked)){
                        return Err("Text contains missing/locked outline; unlock before editing".into());
                    }
                    let obsolete:HashSet<_>=label.outline_ids.iter().copied().collect();
                    next.paths.retain(|p|!obsolete.contains(&p.id));
                    next.text_runs.retain(|run|run.id!=id);
                    id
                }else{
                    let id=next.next_id;
                    next.next_id=id.checked_add(1).ok_or("Text ID exhausted")?;
                    id
                };
                let mut outline_ids=Vec::new();
                for mut p in paths{
                    p.id=next.next_id;
                    next.next_id=next.next_id.checked_add(1)
                        .ok_or("Text outline IDs exhausted")?;
                    outline_ids.push(p.id);
                    next.paths.push(p);
                }
                next.text_runs.push(crate::text::TextRun{
                    id:label_id,spec,outline_ids,
                });
            }
            Action::ConvertContour{id}=>{
                let contour=next.contours.iter().find(|p|p.id==id)
                    .ok_or("Legacy contour ID not found")?;
                if contour.locked{return Err("Unlock contour before converting".into());}
                let mut shape=polyline(contour.id,contour.name.clone(),
                    contour.origin,contour.vertices.clone(),true)?;
                shape.visible=contour.visible;
                shape.validate()?;
                next.contours.retain(|p|p.id!=id);
                next.paths.push(shape);
            }
            Action::DuplicateMany{ids}=>{
                Self::check_batch(&next,&ids)?;
                for id in ids {
                    let new_id=next.next_id;
                    next.next_id=new_id.checked_add(1).ok_or("Vector IDs exhausted")?;
                    if let Some(source)=next.paths.iter().find(|p|p.id==id){
                        let mut copy=source.clone();
                        copy.id=new_id;
                        copy.name=format!("{} copy",source.name);
                        copy.locked=false;
                        copy.origin=copy.origin.offset(8.0,8.0);
                        next.paths.push(copy);
                    }else if let Some(source)=next.contours.iter().find(|p|p.id==id){
                        let mut copy=source.clone();
                        copy.id=new_id;
                        copy.name=format!("{} copy",source.name);
                        copy.locked=false;
                        copy.origin=copy.origin.offset(8.0,8.0);
                        next.contours.push(copy);
                    }
                }
            }
            Action::RemoveMany{ids}=>{
                Self::check_batch(&next,&ids)?;
                let selected:HashSet<u64>=ids.into_iter().collect();
                next.paths.retain(|p|!selected.contains(&p.id));
                next.contours.retain(|p|!selected.contains(&p.id));
            }
            Action::MoveMany{ids,delta}=>{
                Self::check_batch(&next,&ids)?;
                if !delta.finite(){return Err("Group movement must be finite".into());}
                let selected:HashSet<u64>=ids.into_iter().collect();
                for path in &mut next.paths {
                    if selected.contains(&path.id){
                        path.origin=path.origin.offset(delta.x,delta.y);
                    }
                }
                for contour in &mut next.contours {
                    if selected.contains(&contour.id){
                        contour.origin=contour.origin.offset(delta.x,delta.y);
                    }
                }
            }
            Action::Arrange{ids,mode}=>{
                Self::check_batch(&next,&ids)?;
                if !matches!(mode,Arrangement::StockLeft|Arrangement::StockRight|
                    Arrangement::StockHCenter|Arrangement::StockBottom|
                    Arrangement::StockTop|Arrangement::StockVCenter)
                    && ids.len()<2 {
                    return Err("Align at least two vectors or use Align to Stock".into());
                }
                let offsets=arrangement_offsets(&next,&ids,mode)?;
                for (id,delta) in offsets {
                    if let Some(path)=next.paths.iter_mut().find(|p|p.id==id){
                        path.origin=path.origin.offset(delta.x,delta.y);
                    }else if let Some(contour)=next.contours.iter_mut().find(|p|p.id==id){
                        contour.origin=contour.origin.offset(delta.x,delta.y);
                    }
                }
            }
            Action::Duplicate{id}=>{
                let new_id=next.next_id;
                next.next_id=new_id.checked_add(1).ok_or("Duplicate ID exhausted")?;
                if let Some(source)=next.paths.iter().find(|p|p.id==id) {
                    let mut clone=source.clone();
                    clone.id=new_id;
                    clone.name=format!("{} copy",source.name);
                    clone.locked=false;
                    clone.origin=clone.origin.offset(8.0,8.0);
                    next.paths.push(clone);
                }else if let Some(source)=next.contours.iter().find(|p|p.id==id){
                    let mut clone=source.clone();
                    clone.id=new_id;
                    clone.name=format!("{} copy",source.name);
                    clone.locked=false;
                    clone.origin=clone.origin.offset(8.0,8.0);
                    next.contours.push(clone);
                }else{return Err("Nothing selected to duplicate".into());}
            }
            Action::Flip{id,horizontal}=>{
                if let Some(path)=next.paths.iter_mut().find(|p|p.id==id){
                    if path.locked{return Err("Path is locked".into());}
                    let lo=path.nodes.iter().map(|n|if horizontal{n.position.x}
                        else{n.position.y}).fold(f64::INFINITY,f64::min);
                    let hi=path.nodes.iter().map(|n|if horizontal{n.position.x}
                        else{n.position.y}).fold(f64::NEG_INFINITY,f64::max);
                    let reflect=|p:&mut Point|{
                        if horizontal{p.x=lo+hi-p.x;}else{p.y=lo+hi-p.y;}
                    };
                    for node in &mut path.nodes{reflect(&mut node.position);}
                    for seg in &mut path.segments {
                        match &mut seg.curve{
                            Curve::Line=>{},
                            Curve::Arc{center,clockwise}=>{
                                reflect(center);*clockwise=!*clockwise;
                            },
                            Curve::Cubic{control1,control2}=>{
                                reflect(control1);reflect(control2);
                            },
                        }
                    }
                }else if let Some(contour)=next.contours.iter_mut().find(|p|p.id==id){
                    if contour.locked{return Err("Contour is locked".into());}
                    let lo=contour.vertices.iter().map(|n|if horizontal{n.x}else{n.y})
                        .fold(f64::INFINITY,f64::min);
                    let hi=contour.vertices.iter().map(|n|if horizontal{n.x}else{n.y})
                        .fold(f64::NEG_INFINITY,f64::max);
                    for p in &mut contour.vertices{
                        if horizontal {p.x=lo+hi-p.x;}else{p.y=lo+hi-p.y;}
                    }
                }else{return Err("Nothing selected to flip".into());}
            }
            Action::RotateQuarter{id,clockwise}=>{
                if let Some(path)=next.paths.iter_mut().find(|p|p.id==id) {
                    if path.locked{return Err("Path is locked".into());}
                    let bounds=path.nodes.iter().map(|n|n.position);
                    let min_x=bounds.clone().map(|p|p.x).fold(f64::INFINITY,f64::min);
                    let max_x=path.nodes.iter().map(|n|n.position.x)
                        .fold(f64::NEG_INFINITY,f64::max);
                    let min_y=path.nodes.iter().map(|n|n.position.y)
                        .fold(f64::INFINITY,f64::min);
                    let max_y=path.nodes.iter().map(|n|n.position.y)
                        .fold(f64::NEG_INFINITY,f64::max);
                    let pivot=Point::new((min_x+max_x)/2.0,(min_y+max_y)/2.0);
                    let rotate=|p:&mut Point|{
                        let x=p.x-pivot.x;let y=p.y-pivot.y;
                        if clockwise{
                            p.x=pivot.x+y;p.y=pivot.y-x;
                        }else{
                            p.x=pivot.x-y;p.y=pivot.y+x;
                        }
                    };
                    for node in &mut path.nodes{rotate(&mut node.position);}
                    for seg in &mut path.segments{
                        match &mut seg.curve{
                            Curve::Line=>{},
                            Curve::Arc{center,..}=>rotate(center),
                            Curve::Cubic{control1,control2}=>{
                                rotate(control1);rotate(control2);
                            },
                        }
                    }
                }else if let Some(contour)=next.contours.iter_mut().find(|p|p.id==id){
                    if contour.locked{return Err("Contour is locked".into());}
                    let min_x=contour.vertices.iter().map(|p|p.x).fold(f64::INFINITY,f64::min);
                    let max_x=contour.vertices.iter().map(|p|p.x)
                        .fold(f64::NEG_INFINITY,f64::max);
                    let min_y=contour.vertices.iter().map(|p|p.y).fold(f64::INFINITY,f64::min);
                    let max_y=contour.vertices.iter().map(|p|p.y)
                        .fold(f64::NEG_INFINITY,f64::max);
                    let cx=(min_x+max_x)/2.0;let cy=(min_y+max_y)/2.0;
                    for p in &mut contour.vertices{
                        let x=p.x-cx;let y=p.y-cy;
                        if clockwise{p.x=cx+y;p.y=cy-x;}
                        else{p.x=cx-y;p.y=cy+x;}
                    }
                }else{return Err("Nothing selected to rotate".into());}
            }
            Action::Center{id,horizontal,vertical}=>{
                let stock_center=Point::new(next.stock.width_mm*0.5,
                    next.stock.height_mm*0.5);
                if let Some(path)=next.paths.iter_mut().find(|p|p.id==id){
                    if path.locked{return Err("Path is locked".into());}
                    let points=path.preview_points(0.1)?;
                    let min_x=points.iter().map(|p|p.x).fold(f64::INFINITY,f64::min);
                    let max_x=points.iter().map(|p|p.x).fold(f64::NEG_INFINITY,f64::max);
                    let min_y=points.iter().map(|p|p.y).fold(f64::INFINITY,f64::min);
                    let max_y=points.iter().map(|p|p.y).fold(f64::NEG_INFINITY,f64::max);
                    if horizontal{path.origin.x+=stock_center.x-(min_x+max_x)*0.5;}
                    if vertical{path.origin.y+=stock_center.y-(min_y+max_y)*0.5;}
                }else if let Some(contour)=next.contours.iter_mut().find(|p|p.id==id){
                    if contour.locked{return Err("Contour is locked".into());}
                    let points=contour.world_points();
                    let min_x=points.iter().map(|p|p.x).fold(f64::INFINITY,f64::min);
                    let max_x=points.iter().map(|p|p.x).fold(f64::NEG_INFINITY,f64::max);
                    let min_y=points.iter().map(|p|p.y).fold(f64::INFINITY,f64::min);
                    let max_y=points.iter().map(|p|p.y).fold(f64::NEG_INFINITY,f64::max);
                    if horizontal{contour.origin.x+=stock_center.x-(min_x+max_x)*0.5;}
                    if vertical{contour.origin.y+=stock_center.y-(min_y+max_y)*0.5;}
                }else{return Err("Nothing selected to center".into());}
            }
            Action::SetVisible{id,visible}=>{
                if let Some(path)=next.paths.iter_mut().find(|p|p.id==id){
                    path.visible=visible;
                }else if let Some(contour)=next.contours.iter_mut().find(|p|p.id==id){
                    contour.visible=visible;
                }else{return Err("Nothing selected for visibility".into());}
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
                        let _ = path.segments.pop();
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
        // If an outline was individually removed, retain the remaining
        // manually editable curves but detach the now incomplete text source.
        let existing:HashSet<u64>=next.paths.iter().map(|p|p.id).collect();
        next.text_runs.retain(|run|
            run.outline_ids.iter().all(|id|existing.contains(id)));
        next.validate()?;
        if next!=self.project {
            let before=std::mem::replace(&mut self.project,next);
            self.store(before);
        }
        Ok(())
    }
    /// Validate the complete group *before* applying anything. Hidden,
    /// locked, unknown and repeated IDs all fail closed.
    fn check_batch(project:&Project,ids:&[u64])->Result<(),String>{
        if ids.is_empty() || ids.len()>512 {
            return Err("Select 1–512 vectors for a batch edit".into());
        }
        let mut unique=HashSet::new();
        for &id in ids {
            if !unique.insert(id){return Err("Duplicate group object ID".into());}
            let path=project.paths.iter().find(|p|p.id==id);
            let contour=project.contours.iter().find(|p|p.id==id);
            match (path,contour) {
                (Some(p),None) if p.visible&&!p.locked=>{},
                (None,Some(p)) if p.visible&&!p.locked=>{},
                (Some(_),None)|(None,Some(_))=>
                    return Err("Group includes a hidden or locked vector".into()),
                _=>return Err("Group contains an unknown vector ID".into()),
            }
        }
        Ok(())
    }

    pub fn start_group_drag(&mut self,ids:&[u64])->Result<(),String>{
        if self.drag_before.is_some(){return Err("Drag already active".into());}
        Self::check_batch(&self.project,ids)?;
        self.drag_before=Some(self.project.clone());
        Ok(())
    }

    pub fn preview_group_drag(&mut self,ids:&[u64],delta:Point)->Result<(),String>{
        let baseline=self.drag_before.as_ref().ok_or("Group drag not started")?;
        Self::check_batch(baseline,ids)?;
        if !delta.finite(){return Err("Group displacement must be finite".into());}
        let mut next=baseline.clone();
        let selected:HashSet<u64>=ids.iter().copied().collect();
        for path in &mut next.paths{
            if selected.contains(&path.id){
                path.origin=path.origin.offset(delta.x,delta.y);
            }
        }
        for contour in &mut next.contours{
            if selected.contains(&contour.id){
                contour.origin=contour.origin.offset(delta.x,delta.y);
            }
        }
        next.validate()?;
        self.project=next;
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
    pub fn start_control_drag(&mut self,path_id:u64,segment_id:u64,handle:u8)
        ->Result<Point,String>{
        if self.drag_before.is_some(){return Err("Drag already active".into());}
        let path=self.project.paths.iter().find(|p|p.id==path_id)
            .ok_or("Analytic path ID not found")?;
        if path.locked || !path.visible {return Err("Cannot edit hidden or locked path".into());}
        let segment=path.segments.iter().find(|s|s.id==segment_id)
            .ok_or("Segment ID not found")?;
        let pos=match (&segment.curve,handle) {
            (Curve::Cubic{control1,..},1)=>*control1,
            (Curve::Cubic{control2,..},2)=>*control2,
            _=>return Err("Expected cubic control handle one or two".into()),
        };
        self.drag_before=Some(self.project.clone());
        Ok(pos)
    }
    pub fn preview_control_drag(&mut self,path_id:u64,segment_id:u64,handle:u8,position:Point)
        ->Result<(),String>{
        let baseline=self.drag_before.as_ref().ok_or("Drag not started")?;
        let mut candidate=baseline.clone();
        let path=candidate.paths.iter_mut().find(|p|p.id==path_id)
            .ok_or("Analytic path ID not found")?;
        if path.locked{return Err("Path is locked".into());}
        path.move_control(segment_id,handle,position)?;
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
    #[test]
    fn text_creation_edit_undo_and_native_project_roundtrip(){
        let mut e=Editor::default();
        let spec=crate::text::TextSpec{
            text:"NAVY".into(),family:"Example".into(),
            postscript:"Example-Regular".into(),height_mm:20.0,
            tracking_mm:0.5,origin:Point::new(15.0,25.0),
        };
        let a=crate::shapes::create_shape(1,"Glyph A".into(),spec.origin,
            ShapeKind::Rectangle,10.0,15.0).unwrap();
        let b=crate::shapes::create_shape(1,"Glyph B".into(),
            Point::new(28.0,25.0),ShapeKind::Rectangle,9.0,15.0).unwrap();
        let empty=e.project.clone();
        e.apply(Action::SetText{id:None,spec:spec.clone(),
            paths:vec![a.clone(),b.clone()]}).unwrap();
        assert_eq!(e.project.text_runs.len(),1);
        let run=e.project.text_runs[0].clone();
        assert_eq!(run.outline_ids.len(),2);
        assert_eq!(run.id,1);
        assert_eq!(run.outline_ids,vec![2,3]);
        let persisted=crate::Project::decode(&e.project.encode().unwrap()).unwrap();
        assert_eq!(persisted,e.project);
        let mut changed=spec;
        changed.text="N".into();
        e.apply(Action::SetText{id:Some(run.id),spec:changed.clone(),
            paths:vec![a]}).unwrap();
        assert_eq!(e.project.paths.len(),1);
        assert_eq!(e.project.text_runs[0].spec.text,"N");
        assert!(e.undo());
        assert_eq!(e.project,persisted);
        assert!(e.undo());
        assert_eq!(e.project,empty);
        assert!(e.apply(Action::SetText{id:Some(run.id),spec:changed,
            paths:vec![b]}).is_err());
        assert_eq!(e.project,empty);
    }
    #[test]
    fn deleting_a_single_text_outline_detaches_source_but_preserves_other_geometry(){
        let mut e=Editor::default();
        let spec=crate::text::TextSpec{
            text:"A".into(),family:"Example".into(),
            postscript:"Example".into(),height_mm:12.0,
            tracking_mm:0.0,origin:Point::new(1.0,1.0),
        };
        let a=crate::shapes::create_shape(1,"Glyph".into(),spec.origin,
            ShapeKind::Rectangle,10.0,10.0).unwrap();
        e.apply(Action::SetText{id:None,spec,paths:vec![a]}).unwrap();
        assert_eq!(e.project.text_runs.len(),1);
        e.apply(Action::RemovePath{id:2}).unwrap();
        assert!(e.project.text_runs.is_empty());
        assert!(e.undo());
        assert_eq!(e.project.text_runs.len(),1);
        assert_eq!(e.project.paths.len(),1);
    }
    #[test]
    fn svg_import_is_all_or_nothing_one_history_entry(){
        let mut e=Editor::default();
        let mut source=AnalyticPath::preset(1,"Curve".into(),
            Point::new(5.0,5.0),Primitive::Cubic,20.0,10.0).unwrap();
        let before=e.project.clone();
        e.apply(Action::ImportPaths{paths:vec![source.clone(),source.clone()]})
            .unwrap();
        assert_eq!(e.project.paths.len(),2);
        assert_eq!((e.project.paths[0].id,e.project.paths[1].id),(1,2));
        assert!(e.undo());
        assert_eq!(e.project,before);
        source.nodes[0].position.x=f64::NAN;
        assert!(e.apply(Action::ImportPaths{paths:vec![source]}).is_err());
        assert_eq!(e.project,before);
    }
    fn rect() -> Action {
        Action::AddRectangle{name:"Panel".into(),origin:Point::new(20.,30.),
            width_mm:50.,height_mm:20.}
    }


    #[test]
    fn precision_arrange_preserves_editable_curves_and_one_step_undo(){
        let mut e=Editor::default();
        e.apply(Action::AddShape{kind:ShapeKind::Rectangle,
            name:"Panel".into(),origin:Point::new(10.0,10.0),
            width_mm:40.0,height_mm:30.0}).unwrap();
        e.apply(Action::AddAnalytic{name:"Cubic".into(),
            origin:Point::new(95.0,55.0),kind:Primitive::Cubic,
            width_mm:50.0,height_mm:20.0}).unwrap();
        e.apply(Action::AddRectangle{name:"Legacy".into(),
            origin:Point::new(180.0,80.0),width_mm:20.0,height_mm:10.0}).unwrap();
        let initial=e.project.clone();
        e.apply(Action::Arrange{ids:vec![1,2,3],mode:Arrangement::Bottom}).unwrap();
        for id in [1,2,3]{
            let b=crate::arrange::vector_bounds(&e.project,id).unwrap();
            assert!((b.min.y-10.0).abs()<1e-8);
        }
        assert!(e.project.paths[1].segments.iter()
            .all(|s|matches!(s.curve,Curve::Cubic{..})));
        assert!(e.undo());
        assert_eq!(e.project,initial);
        e.apply(Action::Arrange{ids:vec![1,2,3],mode:Arrangement::StockHCenter}).unwrap();
        let lo=(1..=3).map(|id|crate::arrange::vector_bounds(&e.project,id).unwrap().min.x)
            .fold(f64::INFINITY,f64::min);
        let hi=(1..=3).map(|id|crate::arrange::vector_bounds(&e.project,id).unwrap().max.x)
            .fold(f64::NEG_INFINITY,f64::max);
        assert!(((lo+hi)/2.0-e.project.stock.width_mm/2.0).abs()<1e-8);
        assert!(e.undo());
        assert_eq!(e.project,initial);
    }
    #[test]
    fn arrangement_rejects_locked_unknown_and_single_vector_selection(){
        let mut e=Editor::default();
        for i in 0..3 {
            e.apply(Action::AddShape{kind:ShapeKind::Rectangle,
                name:format!("Rect {i}"),origin:Point::new(i as f64*45.0,20.0),
                width_mm:20.0,height_mm:15.0}).unwrap();
        }
        e.apply(Action::SetPathLocked{id:2,locked:true}).unwrap();
        let before=e.project.clone();
        for ids in [vec![1],vec![1,2,3],vec![1,1],vec![1,99]]{
            assert!(e.apply(Action::Arrange{ids,mode:Arrangement::Left}).is_err());
            assert_eq!(e.project,before);
        }
        assert!(e.apply(Action::Arrange{ids:vec![1,2,3],
            mode:Arrangement::DistributeX}).is_err());
    }
    #[test]
    fn batch_selection_drag_is_atomic_across_paths_and_legacy_contours(){
        let mut e=Editor::default();
        e.apply(Action::AddShape{kind:ShapeKind::Circle,
            name:"Circle".into(),origin:Point::new(10.0,20.0),
            width_mm:20.0,height_mm:20.0}).unwrap();
        e.apply(Action::AddRectangle{name:"Old rectangle".into(),
            origin:Point::new(50.0,40.0),width_mm:30.0,height_mm:10.0}).unwrap();
        let original=e.project.clone();
        e.start_group_drag(&[1,2]).unwrap();
        e.preview_group_drag(&[1,2],Point::new(5.0,7.0)).unwrap();
        e.preview_group_drag(&[1,2],Point::new(9.0,11.0)).unwrap();
        assert_eq!(e.project.paths[0].origin,Point::new(19.0,31.0));
        assert_eq!(e.project.contours[0].origin,Point::new(59.0,51.0));
        assert!(e.preview_group_drag(&[1,2],Point::new(f64::NAN,0.0)).is_err());
        assert_eq!(e.project.paths[0].origin,Point::new(19.0,31.0));
        e.finish_drag();
        assert!(e.undo());
        assert_eq!(e.project,original);
        assert!(e.redo());
        assert_eq!(e.project.paths[0].origin,Point::new(19.0,31.0));
    }
    #[test]
    fn batch_fail_closed_for_locked_hidden_missing_and_duplicate_ids(){
        let mut e=Editor::default();
        e.apply(Action::AddShape{kind:ShapeKind::Triangle,
            name:"Triangle".into(),origin:Point::new(10.0,10.0),
            width_mm:30.0,height_mm:30.0}).unwrap();
        e.apply(Action::AddShape{kind:ShapeKind::Rectangle,
            name:"Panel".into(),origin:Point::new(70.0,30.0),
            width_mm:25.0,height_mm:25.0}).unwrap();
        e.apply(Action::SetPathLocked{id:2,locked:true}).unwrap();
        let baseline=e.project.clone();
        for ids in [vec![],vec![1,1],vec![1,2],vec![1,99]]{
            assert!(e.start_group_drag(&ids).is_err());
            assert!(e.apply(Action::MoveMany{ids,
                delta:Point::new(5.0,3.0)}).is_err());
            assert_eq!(e.project,baseline);
        }
        e.apply(Action::SetPathLocked{id:2,locked:false}).unwrap();
        e.apply(Action::SetVisible{id:2,visible:false}).unwrap();
        assert!(e.start_group_drag(&[1,2]).is_err());
    }
    #[test]
    fn batch_duplicate_and_delete_each_use_one_undo_step(){
        let mut e=Editor::default();
        for (id,kind) in [ShapeKind::Star,ShapeKind::Ellipse].into_iter().enumerate(){
            e.apply(Action::AddShape{kind,name:format!("Shape {id}"),
                origin:Point::new(10.0+id as f64*40.0,20.0),
                width_mm:30.0,height_mm:25.0}).unwrap();
        }
        let original=e.project.clone();
        e.apply(Action::DuplicateMany{ids:vec![1,2]}).unwrap();
        assert_eq!(e.project.paths.len(),4);
        assert_eq!(e.project.paths[2].id,3);
        assert_eq!(e.project.paths[3].id,4);
        assert!(e.project.paths[3].segments.iter()
            .all(|s|matches!(s.curve,Curve::Cubic{..})));
        e.apply(Action::RemoveMany{ids:vec![1,2]}).unwrap();
        assert_eq!(e.project.paths.len(),2);
        assert!(e.undo());
        assert_eq!(e.project.paths.len(),4);
        assert!(e.undo());
        assert_eq!(e.project,original);
    }

    #[test]
    fn object_and_project_renaming_are_atomic_and_undoable(){
        let mut e=Editor::default();
        e.apply(Action::AddShape{kind:ShapeKind::Rectangle,
            name:"Unnamed".into(),origin:Point::new(0.0,0.0),
            width_mm:20.0,height_mm:10.0}).unwrap();
        e.apply(Action::RenamePath{id:1,name:"Top pocket".into()}).unwrap();
        e.apply(Action::RenameProject{name:"Wall sign".into()}).unwrap();
        assert_eq!(e.project.paths[0].name,"Top pocket");
        assert_eq!(e.project.name,"Wall sign");
        let snapshot=e.project.clone();
        assert!(e.apply(Action::RenamePath{id:1,name:"".into()}).is_err());
        assert!(e.apply(Action::RenameProject{name:" ".into()}).is_err());
        assert_eq!(e.project,snapshot);
        assert!(e.undo());
        assert_eq!(e.project.name,"Untitled CNC design");
        assert!(e.undo());
        assert_eq!(e.project.paths[0].name,"Unnamed");
        assert!(e.redo());
        assert_eq!(e.project.paths[0].name,"Top pocket");
    }
    #[test]
    fn all_creation_tools_create_editable_paths_and_preserve_history(){
        let mut e=Editor::default();
        for kind in [ShapeKind::Rectangle,ShapeKind::Triangle,ShapeKind::Hexagon,
            ShapeKind::Pentagon,ShapeKind::Octagon,ShapeKind::Star,
            ShapeKind::Ellipse,ShapeKind::Circle] {
            e.apply(Action::AddShape{kind,name:kind.title().into(),
                origin:Point::new(5.0,5.0),width_mm:40.0,height_mm:30.0}).unwrap();
        }
        assert_eq!(e.project.paths.len(),8);
        assert!(e.project.paths.iter().all(|p|p.closed));
        assert_eq!(Project::decode(&e.project.encode().unwrap()).unwrap(),e.project);
    }
    #[test]
    fn copy_flip_center_visibility_are_undoable_and_preserve_curves(){
        let mut e=Editor::default();
        e.apply(Action::AddShape{kind:ShapeKind::Ellipse,name:"Oval".into(),
            origin:Point::new(8.0,12.0),width_mm:40.0,height_mm:30.0}).unwrap();
        e.apply(Action::Duplicate{id:1}).unwrap();
        assert_eq!(e.project.paths.len(),2);
        assert_eq!(e.project.paths[1].id,2);
        let before=e.project.clone();
        e.apply(Action::Flip{id:2,horizontal:true}).unwrap();
        assert!(e.project.paths[1].segments.iter()
            .all(|s|matches!(s.curve,Curve::Cubic{..})));
        e.apply(Action::RotateQuarter{id:2,clockwise:true}).unwrap();
        e.apply(Action::RotateQuarter{id:2,clockwise:false}).unwrap();
        assert!(e.project.paths[1].segments.iter()
            .all(|s|matches!(s.curve,Curve::Cubic{..})));
        e.apply(Action::Center{id:2,horizontal:true,vertical:true}).unwrap();
        e.apply(Action::SetVisible{id:2,visible:false}).unwrap();
        assert!(!e.project.paths[1].visible);
        assert!(e.undo());
        assert!(e.project.paths[1].visible);
        assert!(e.undo()); // Center
        assert!(e.undo()); // Reverse rotation
        assert!(e.undo()); // Forward rotation
        assert!(e.undo()); // Flip
        assert_eq!(e.project,before);
    }
    #[test]
    fn existing_r0_contours_can_be_converted_losslessly_to_editable_paths(){
        let mut e=Editor::default();
        e.apply(Action::AddRectangle{
            name:"Legacy rectangle".into(),origin:Point::new(12.0,18.0),
            width_mm:30.0,height_mm:15.0,
        }).unwrap();
        let before=e.project.clone();
        e.apply(Action::ConvertContour{id:1}).unwrap();
        assert!(e.project.contours.is_empty());
        assert_eq!(e.project.paths[0].id,1);
        assert_eq!(e.project.paths[0].nodes.len(),4);
        assert_eq!(e.project.paths[0].origin,Point::new(12.0,18.0));
        e.apply(Action::MoveNode{path_id:1,node_id:1,
            position:Point::new(-2.0,0.0)}).unwrap();
        assert!(e.undo());
        assert!(e.undo());
        assert_eq!(e.project,before);
    }
    #[test]
    fn freeform_polyline_and_locked_tools_fail_closed(){
        let mut e=Editor::default();
        e.apply(Action::AddPolyline{name:"Sketch".into(),closed:false,
            points:vec![Point::new(2.0,3.0),Point::new(6.0,3.0),
                Point::new(8.0,10.0)]}).unwrap();
        assert_eq!(e.project.paths[0].segments.len(),2);
        e.apply(Action::SetPathLocked{id:1,locked:true}).unwrap();
        let source=e.project.clone();
        for action in [Action::Flip{id:1,horizontal:true},
            Action::Center{id:1,horizontal:true,vertical:true}] {
            assert!(e.apply(action).is_err());
            assert_eq!(e.project,source);
        }
    }
    #[test]
    fn cubic_control_drag_is_atomic_and_undoable() {
        let mut e=Editor::default();
        e.apply(Action::AddAnalytic{name:"Cubic".into(),
            origin:Point::new(0.0,0.0),kind:Primitive::Cubic,
            width_mm:50.0,height_mm:25.0}).unwrap();
        let original=e.project.clone();
        let control=e.start_control_drag(1,3,1).unwrap();
        e.preview_control_drag(1,3,1,control.offset(3.0,5.0)).unwrap();
        assert!(e.preview_control_drag(1,3,1,Point::new(f64::INFINITY,0.0)).is_err());
        e.finish_drag();
        assert!(e.undo());
        assert_eq!(e.project,original);
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
    fn editing_arc_anchors_refits_circle_with_undo_and_atomic_drag(){
        let mut e=Editor::default();
        e.apply(Action::AddAnalytic{name:"Arch".into(),
            origin:Point::new(0.0,0.0),kind:Primitive::Arc,
            width_mm:50.0,height_mm:20.0}).unwrap();
        let before=e.project.clone();
        e.apply(Action::MoveNode{path_id:1,node_id:1,
            position:Point::new(2.0,2.0)}).unwrap();
        e.project.paths[0].validate().unwrap();
        assert!(e.undo());
        assert_eq!(e.project,before);
        let anchor=e.start_node_drag(1,1).unwrap();
        e.preview_node_drag(1,1,anchor.offset(2.0,1.0)).unwrap();
        e.finish_drag();
        assert!(e.undo());
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
