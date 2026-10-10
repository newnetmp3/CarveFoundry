//! CarveFoundry reboot: an independent, 100% Rust desktop and project model.
//! This version cannot generate toolpaths, preflight machine motion or post NC.
mod ui;
use carvefoundry_core::{Action,Editor,Hit,Point,Primitive,Project,ShapeKind,TextSpec};
use eframe::egui;
use egui::Vec2;
use std::{path::Path,collections::BTreeSet,fs};

#[derive(Clone, Copy, PartialEq, Eq)]
enum EditMode { Objects, Nodes, Draw }
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum Workspace { Drawing, Toolpaths }
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum InspectorTab { Objects, Layers, Properties, Job }
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum PendingDocument { New, Open }
#[derive(Clone)]
enum ActiveDrag {
    None,
    Contour(u64,Point),
    Path(u64,Point),
    Node(u64,u64,Point),
    Control(u64,u64,u8,Point),
    Group(Vec<u64>),
}
struct Studio {
    editor: Editor,
    saved_project: Project,
    has_saved_file: bool,
    project_path: String,
    rename_target: Option<u64>,
    rename_draft: String,
    group_name_draft:String,
    layer_name_draft:String,
    active_group_id:Option<u64>,
    active_layer_id:Option<u64>,
    project_name_draft: String,
    workspace: Workspace,
    inspector_tab: InspectorTab,
    show_grid: bool,
    show_help: bool,
    font_database: fontdb::Database,
    font_choices: Vec<ui::text::FaceChoice>,
    font_scanned:bool,
    text_dialog:bool,
    text_edit_id:Option<u64>,
    text_error:String,
    text_spec:TextSpec,
    pending_document: Option<PendingDocument>,
    pending_open_path: Option<String>,
    cursor_world: Option<Point>,
    selected: Option<u64>,
    selected_ids:BTreeSet<u64>,
    marquee_start:Option<Point>,
    marquee_extend:bool,
    snap_features:bool,
    selected_path: Option<u64>,
    selected_node: Option<u64>,
    selected_handle: Option<(u64,u8)>,
    edit_mode: EditMode,
    active_shape: Option<ShapeKind>,
    exact_shape_placement: bool,
    shape_drag_start: Option<Point>,
    shape_drag_delta: Option<Point>,
    shape_name: String,
    shape_width: f64,
    shape_height: f64,
    zoom: f32,
    pan: Vec2,
    canvas_size:Vec2,
    grid_step: f64,
    use_grid: bool,
    nudge_mm:f64,
    precise_selection:Vec<u64>,
    precise_x:f64,
    precise_y:f64,
    drag: Option<ActiveDrag>,
    drawing: Vec<Point>,
    draw_closed: bool,
    status: String,
}
impl Default for Studio {
    fn default() -> Self {
        Self {
            editor: Editor::default(),
            saved_project: Project::default(),
            has_saved_file: false,
            project_path: "untitled.cfd".into(),
            rename_target: None,
            rename_draft: String::new(),
            group_name_draft:"New group".into(),
            layer_name_draft:"New layer".into(),
            active_group_id:None,active_layer_id:None,
            project_name_draft: Project::default().name,
            workspace: Workspace::Drawing,
            inspector_tab: InspectorTab::Objects,
            show_grid: true,
            show_help: false,
            font_database:fontdb::Database::new(),
            font_choices:Vec::new(),font_scanned:false,
            text_dialog:false,text_edit_id:None,text_error:String::new(),
            text_spec:TextSpec{text:"US NAVY".into(),family:String::new(),
                postscript:String::new(),height_mm:24.0,tracking_mm:0.0,
                origin:Point::new(20.0,80.0)},
            pending_document: None,
            pending_open_path: None,
            cursor_world: None,
            selected: None,
            selected_ids:BTreeSet::new(),
            marquee_start:None,
            marquee_extend:false,
            snap_features:true,
            selected_path: None,
            selected_node: None,
            selected_handle: None,
            edit_mode: EditMode::Objects,
            active_shape: None,
            exact_shape_placement: false,
            shape_drag_start: None,
            shape_drag_delta: None,
            shape_name: "New vector".into(),
            shape_width: 50.0, shape_height: 30.0,
            zoom: 1.0, pan:Vec2::ZERO, canvas_size:Vec2::new(900.0,650.0), grid_step: 1.0, use_grid: false,
            nudge_mm:1.0,precise_selection:Vec::new(),precise_x:0.0,precise_y:0.0,
            drag: None,
            drawing: Vec::new(),
            draw_closed: false,
            status: "Ready · Rust design file only · CNC export disabled".into(),
        }
    }
}
impl Studio {
    fn apply(&mut self, action: Action) {
        match self.editor.apply(action) {
            Ok(()) => self.status = "Design changed · No machine toolpaths exist".into(),
            Err(reason) => self.status = format!("Edit rejected: {reason}"),
        }
    }
    fn new_document(&mut self) {
        self.editor = Editor::default();
        self.saved_project=self.editor.project.clone();
        self.project_path="untitled.cfd".into();
        self.has_saved_file=false;
        self.project_name_draft=self.editor.project.name.clone();
        self.rename_target=None;
        self.rename_draft.clear();
        self.active_group_id=None;
        self.active_layer_id=None;
        self.workspace=Workspace::Drawing;
        self.inspector_tab=InspectorTab::Objects;
        self.pending_document=None;
        self.pending_open_path=None;
        self.selected = None;
        self.selected_ids.clear();
        self.marquee_start=None;
        self.selected_path = None;
        self.selected_node = None;
        self.selected_handle = None;
        self.drag = None;
        self.active_shape=None;
        self.exact_shape_placement=false;
        self.shape_drag_start=None;
        self.shape_drag_delta=None;
        self.drawing.clear();
        self.pan=Vec2::ZERO;self.zoom=1.0;
        self.status = "New independent Rust design · No legacy CF3D converter".into();
    }
    fn open_document(&mut self) {
        match Project::open(Path::new(&self.project_path))
            .and_then(Editor::new) {
            Ok(editor) => {
                self.editor = editor;
                self.saved_project=self.editor.project.clone();
                self.has_saved_file=true;
                self.project_name_draft=self.editor.project.name.clone();
                self.rename_target=None;
                self.rename_draft.clear();
                self.workspace=Workspace::Drawing;
                self.inspector_tab=InspectorTab::Objects;
                self.pending_document=None;
                self.pending_open_path=None;
                self.selected = None;
                self.selected_ids.clear();
                self.marquee_start=None;
                self.selected_path = None;
                self.selected_node = None;
                self.selected_handle = None;
                self.drag = None;
                self.active_shape=None;
                self.exact_shape_placement=false;
                self.shape_drag_start=None;
                self.shape_drag_delta=None;
                self.drawing.clear();
                self.pan=Vec2::ZERO;self.zoom=1.0;
                self.status = "Opened native Rust design; CNC machining not implemented".into();
            }
            Err(error) => self.status = format!("Open rejected; original design kept: {error}"),
        }
    }
    fn save_document(&mut self) {
        self.status = match self.editor.project.save(Path::new(&self.project_path)) {
            Ok(()) => {
                self.saved_project=self.editor.project.clone();
                self.has_saved_file=true;
                format!("Saved native Rust design to {}",self.project_path)
            }
            Err(error) => format!("Save failed: {error}"),
        };
    }
    fn save_command(&mut self){
        if self.has_saved_file{self.save_document();}
        else{self.choose_save_as();}
    }
    fn request_document(&mut self,command:PendingDocument) {
        if self.editor.project!=self.saved_project {
            self.pending_document=Some(command);
        }else{
            match command {
                PendingDocument::New=>self.new_document(),
                PendingDocument::Open=>self.open_document(),
            }
        }
    }
    fn choose_open_document(&mut self){
        let choice=rfd::FileDialog::new()
            .add_filter("CarveFoundry design", &["cfd"])
            .pick_file();
        if let Some(path)=choice{
            let destination=path.to_string_lossy().into_owned();
            if self.editor.project!=self.saved_project{
                self.pending_open_path=Some(destination);
                self.pending_document=Some(PendingDocument::Open);
            }else{
                self.project_path=destination;
                self.open_document();
            }
        }
    }
    fn choose_save_as(&mut self){
        let initial=Path::new(&self.project_path)
            .file_name().and_then(|x|x.to_str())
            .filter(|n|!n.is_empty()).unwrap_or("design.cfd");
        let choice=rfd::FileDialog::new()
            .add_filter("CarveFoundry design",&["cfd"])
            .set_file_name(initial)
            .save_file();
        if let Some(mut path)=choice{
            if path.extension().is_none(){path.set_extension("cfd");}
            self.project_path=path.to_string_lossy().into_owned();
            self.save_document();
        }
    }
    /// SVG import merges editable paths into the current design, preserving
    /// the original .cfd identity and recording exactly one Undo operation.
    fn import_svg_bytes(&mut self,bytes:&[u8])->Result<usize,String>{
        let vectors=carvefoundry_core::import_svg(bytes)?;
        let count=vectors.paths.len();
        let width=vectors.width_mm;
        let height=vectors.height_mm;
        let start=self.editor.project.next_id;
        self.editor.apply(Action::ImportPaths{paths:vectors.paths})?;
        self.selected_ids=(start..start+count as u64).collect();
        self.selected=None;
        self.selected_path=None;
        self.selected_node=None;
        self.selected_handle=None;
        self.reconcile_selection();
        self.edit_mode=EditMode::Objects;
        self.active_shape=None;
        self.inspector_tab=InspectorTab::Objects;
        self.status=format!("Imported {count} SVG paths ({width:.2} × {height:.2} mm SVG canvas). Design stock unchanged; CNC export disabled");
        Ok(count)
    }
    fn choose_import_svg(&mut self){
        let choice=rfd::FileDialog::new()
            .add_filter("SVG vector paths",&["svg"]).pick_file();
        if let Some(path)=choice{
            let result=(||{
                let meta=fs::metadata(&path).map_err(|e|e.to_string())?;
                if meta.len()>16*1024*1024{
                    return Err("SVG exceeds 16 MiB limit".to_string());
                }
                let bytes=fs::read(&path).map_err(|e|e.to_string())?;
                self.import_svg_bytes(&bytes)
            })();
            if let Err(error)=result{
                self.status=format!("SVG import rejected; design unchanged: {error}");
            }
        }
    }
    /// Add a fully validated DXF as one undoable design edit.
    /// Source stock, fixtures and native .cfd identity remain unchanged.
    fn import_dxf_bytes(&mut self,bytes:&[u8])->Result<usize,String>{
        let vectors=carvefoundry_core::import_dxf(bytes)?;
        let count=vectors.paths.len();
        let units=vectors.units;
        let start=self.editor.project.next_id;
        self.editor.apply(Action::ImportPaths{paths:vectors.paths})?;
        self.selected_ids=(start..start+count as u64).collect();
        self.selected=None;
        self.selected_path=None;
        self.selected_node=None;
        self.selected_handle=None;
        self.reconcile_selection();
        self.edit_mode=EditMode::Objects;
        self.active_shape=None;
        self.inspector_tab=InspectorTab::Objects;
        self.status=format!("Imported {count} editable DXF vectors (source units: {units}); material unchanged. CNC output disabled");
        Ok(count)
    }
    fn choose_import_dxf(&mut self){
        let choice=rfd::FileDialog::new()
            .add_filter("DXF vector drawing",&["dxf"]).pick_file();
        if let Some(path)=choice{
            let result=(||{
                let meta=fs::metadata(&path).map_err(|e|e.to_string())?;
                if meta.len()>16*1024*1024 {
                    return Err("DXF exceeds the 16 MiB limit".to_string());
                }
                let bytes=fs::read(&path).map_err(|e|e.to_string())?;
                self.import_dxf_bytes(&bytes)
            })();
            if let Err(error)=result{
                self.status=format!("DXF import rejected; design unchanged: {error}");
            }
        }
    }
    fn choose_export_dxf(&mut self){
        let initial=Path::new(&self.project_path).file_stem()
            .and_then(|s|s.to_str()).filter(|s|!s.is_empty())
            .unwrap_or("drawing");
        let choice=rfd::FileDialog::new()
            .add_filter("DXF vector drawing",&["dxf"])
            .set_file_name(format!("{initial}.dxf")).save_file();
        if let Some(mut path)=choice{
            if path.extension().is_none(){path.set_extension("dxf");}
            let result=carvefoundry_core::export_dxf(&self.editor.project)
                .and_then(|dxf|fs::write(&path,dxf).map_err(|e|e.to_string()));
            self.status=match result{
                Ok(())=>format!("Exported editable 2D DXF to {}",path.display()),
                Err(error)=>format!("DXF export failed: {error}"),
            };
        }
    }

    fn choose_export_svg(&mut self){
        let initial=Path::new(&self.project_path).file_stem()
            .and_then(|v|v.to_str()).filter(|s|!s.is_empty())
            .unwrap_or("drawing");
        let choice=rfd::FileDialog::new()
            .add_filter("SVG vector drawing",&["svg"])
            .set_file_name(format!("{initial}.svg")).save_file();
        if let Some(mut path)=choice{
            if path.extension().is_none(){path.set_extension("svg");}
            let result=carvefoundry_core::export_svg(&self.editor.project)
                .and_then(|svg|fs::write(&path,svg).map_err(|e|e.to_string()));
            self.status=match result{
                Ok(())=>format!("Exported native analytic SVG to {}",path.display()),
                Err(error)=>format!("SVG export failed: {error}"),
            };
        }
    }
    fn duplicate_selection(&mut self){
        if self.selected_ids.len()>1{
            let before=self.editor.project.next_id;
            let count=self.selected_ids.len();
            let ids=self.selected_ids.iter().copied().collect();
            self.apply(Action::DuplicateMany{ids});
            if self.editor.project.next_id==before+count as u64{
                self.selected_ids=(before..before+count as u64).collect();
                self.selected_path=None;self.selected=None;
                self.reconcile_selection();
            }
        }else if let Some(id)=self.selected_id(){
            let next=self.editor.project.next_id;
            self.apply(Action::Duplicate{id});
            if self.editor.project.paths.iter().any(|p|p.id==next)
                ||self.editor.project.contours.iter().any(|p|p.id==next){
                self.select_vector(Some(next),false);
            }
        }
    }
    fn fit_selection(&mut self){
        let Some((lo,hi))=self.selection_envelope()else{
            self.status="Select one or more vectors to fit them in view".into();
            return;
        };
        let stock=&self.editor.project.stock;
        let base=(((self.canvas_size.x-60.0)/stock.width_mm as f32)
            .min((self.canvas_size.y-60.0)/stock.height_mm as f32))
            .max(0.0001);
        let width=(hi.x-lo.x).max(1.0) as f32;
        let height=(hi.y-lo.y).max(1.0) as f32;
        let scale=(((self.canvas_size.x-100.0).max(20.0)/width)
            .min((self.canvas_size.y-100.0).max(20.0)/height)).max(0.0001);
        self.zoom=(scale/base).clamp(0.25,8.0);
        let actual=base*self.zoom;
        let center_x=(lo.x+hi.x) as f32*0.5;
        let center_y=(lo.y+hi.y) as f32*0.5;
        self.pan=Vec2::new((stock.width_mm as f32*0.5-center_x)*actual,
            (center_y-stock.height_mm as f32*0.5)*actual);
        self.status=format!("Fitted {} selected vectors into the drawing view",
            self.selected_ids.len());
    }

    fn selected_vector_ids(&self)->Vec<u64>{
        self.selected_ids.iter().copied().collect()
    }
    fn arrange_selection(&mut self,mode:carvefoundry_core::Arrangement){
        let ids=self.selected_vector_ids();
        self.apply(Action::Arrange{ids,mode});
        self.precise_selection.clear();
    }
    fn move_selection(&mut self,delta:Point){
        let ids=self.selected_vector_ids();
        if ids.is_empty(){
            self.status="Select at least one editable vector to move".into();
        }else if !delta.finite(){
            self.status="Movement exceeds finite coordinate limits".into();
        }else{
            self.apply(Action::MoveMany{ids,delta});
            self.precise_selection.clear();
        }
    }
    fn delete_selection(&mut self){
        if self.selected_ids.len()>1{
            let ids=self.selected_ids.iter().copied().collect();
            self.apply(Action::RemoveMany{ids});
            self.reconcile_selection();
            return;
        }
        if let Some(id)=self.selected_path {
            self.apply(Action::RemovePath{id});
            if !self.editor.project.paths.iter().any(|p|p.id==id){
                self.selected_path=None;self.selected_node=None;
                self.selected_handle=None;
                self.reconcile_selection();
            }
        }else if let Some(id)=self.selected{
            self.apply(Action::Remove{id});
            if !self.editor.project.contours.iter().any(|p|p.id==id){
                self.selected=None;
                self.reconcile_selection();
            }
        }
    }
    fn reconcile_selection(&mut self){
        self.selected_ids.retain(|id|
            self.editor.project.paths.iter().any(|p|p.id==*id)
            ||self.editor.project.contours.iter().any(|p|p.id==*id));
        let primary=self.selected_id().filter(|id|self.selected_ids.contains(id))
            .or_else(||self.selected_ids.iter().next_back().copied());
        self.selected_path=primary.filter(|id|
            self.editor.project.paths.iter().any(|p|p.id==*id));
        self.selected=primary.filter(|id|
            self.editor.project.contours.iter().any(|p|p.id==*id));
        if self.selected_ids.is_empty(){
            self.selected_node=None;self.selected_handle=None;
        }
    }
    fn select_vector(&mut self,id:Option<u64>,additive:bool){
        if !additive{self.selected_ids.clear();}
        if let Some(id)=id{
            let expanded=if self.edit_mode==EditMode::Objects{
                self.editor.project.expand_groups([id])
            }else{vec![id]};
            let all_present=expanded.iter().all(|id|self.selected_ids.contains(id));
            for member in expanded{
                if additive && all_present{
                    self.selected_ids.remove(&member);
                }else{
                    self.selected_ids.insert(member);
                }
            }
        }
        self.selected_path=None;self.selected=None;
        self.reconcile_selection();
        if let Some(id)=id.filter(|id|self.selected_ids.contains(id)){
            self.selected_path=self.editor.project.paths.iter()
                .any(|p|p.id==id).then_some(id);
            self.selected=self.editor.project.contours.iter()
                .any(|p|p.id==id).then_some(id);
        }
        self.selected_node=None;self.selected_handle=None;
    }
    fn selected_id(&self)->Option<u64> {
        self.selected_path.or(self.selected)
    }
    fn add_shape(&mut self,kind:ShapeKind){
        let id=self.editor.project.next_id;
        let offset=10.0+(self.editor.project.paths.len()%8) as f64*12.0;
        let size=if kind==ShapeKind::Circle {
            self.shape_width.min(self.shape_height)
        }else{self.shape_width};
        self.apply(Action::AddShape{
            kind,name:format!("{} {}",self.shape_name,kind.title()),
            origin:Point::new(offset,offset),width_mm:size,
            height_mm:if kind==ShapeKind::Circle{size}else{self.shape_height},
        });
        if self.editor.project.paths.iter().any(|p|p.id==id){
            self.select_vector(Some(id),false);
            self.edit_mode=EditMode::Objects;
        }
    }
    fn choose_shape_tool(&mut self,kind:ShapeKind){
        self.active_shape=Some(kind);
        self.exact_shape_placement=false;
        self.shape_drag_start=None;
        self.shape_drag_delta=None;
        self.edit_mode=EditMode::Objects;
        self.drawing.clear();
        self.drag=None;
        self.status=format!("{}: drag a diagonal on the material. Shift constrains proportions; Esc cancels.",
            kind.title());
    }
    fn choose_exact_shape_placement(&mut self,kind:ShapeKind){
        self.choose_shape_tool(kind);
        self.exact_shape_placement=true;
        self.status=format!("{}: click a starting position on the stock to place a {:.2} × {:.2} mm vector.",
            kind.title(),self.shape_width,self.shape_height);
    }
    fn create_drag_shape(&mut self,kind:ShapeKind,placement:carvefoundry_core::ShapePlacement){
        let id=self.editor.project.next_id;
        self.apply(Action::AddShape{
            kind,name:format!("{} {}",self.shape_name,kind.title()),
            origin:placement.origin,width_mm:placement.width_mm,
            height_mm:placement.height_mm,
        });
        if self.editor.project.paths.iter().any(|p|p.id==id){
            self.select_vector(Some(id),false);
            self.inspector_tab=InspectorTab::Properties;
            self.shape_width=placement.width_mm;
            self.shape_height=placement.height_mm;
            self.status=format!("Created {}: {:.2} × {:.2} mm. Drag again to add another.",
                kind.title(),placement.width_mm,placement.height_mm);
        }
    }
    fn finish_drawing(&mut self){
        let points=std::mem::take(&mut self.drawing);
        if points.is_empty(){return;}
        let id=self.editor.project.next_id;
        self.apply(Action::AddPolyline {
            name:format!("{} Polyline",self.shape_name),points:points.clone(),
            closed:self.draw_closed,
        });
        if self.editor.project.paths.iter().any(|p|p.id==id){
            self.select_vector(Some(id),false);
            self.edit_mode=EditMode::Nodes;
        }else {
            self.drawing=points;
        }
    }
    fn apply_canvas_hit(&mut self,hit:Option<Hit>,additive:bool){
        match hit {
            Some(Hit::Node{path_id,node_id})=>{
                self.select_vector(Some(path_id),false);
                self.selected_node=Some(node_id);
                self.inspector_tab=InspectorTab::Properties;
            }
            Some(Hit::Handle{path_id,segment_id,handle})=>{
                self.select_vector(Some(path_id),false);
                self.selected_handle=Some((segment_id,handle));
                self.inspector_tab=InspectorTab::Properties;
            }
            Some(Hit::Path(id))=>self.select_vector(Some(id),additive),
            Some(Hit::Contour(id))=>self.select_vector(Some(id),additive),
            None=>self.select_vector(None,additive),
        }
    }
    fn select_entire_group(&mut self,id:u64){
        if let Some(group)=self.editor.project.groups.iter().find(|g|g.id==id){
            self.selected_ids=group.members.iter().copied().collect();
            self.selected_path=None;self.selected=None;
            self.selected_node=None;self.selected_handle=None;
            self.edit_mode=EditMode::Objects;
            self.reconcile_selection();
        }
    }
    fn run_selected(&mut self,action:impl FnOnce(u64)->Action){
        if self.selected_ids.len()!=1{
            self.status="This operation requires exactly one selected vector".into();
        }else if let Some(id)=self.selected_id(){
            self.apply(action(id));
        }
    }
    fn add_analytic(&mut self,kind:Primitive){
        let id=self.editor.project.next_id;
        let position=10.0+(self.editor.project.paths.len()%10) as f64*12.0;
        self.apply(Action::AddAnalytic{
            name:format!("{} {}",self.shape_name,match kind {
                Primitive::Line=>"Line",Primitive::Arc=>"Arc",Primitive::Cubic=>"Bézier",
            }),
            origin:Point::new(position,position),
            kind,width_mm:self.shape_width,height_mm:self.shape_height,
        });
        if self.editor.project.paths.iter().any(|p|p.id==id){
            self.select_vector(Some(id),false);
            self.selected_node=Some(1);
            self.selected_handle=None;
            self.edit_mode=EditMode::Nodes;
        }
    }
    fn keyboard(&mut self,ui:&egui::Ui){
        if ui.ctx().egui_wants_keyboard_input(){return;}
        let (undo,redo,duplicate,select_all,delete,escape,enter,v,n,p,fit,fit_selected,new,open,save,r,c,arrows,coarse)=ui.input(|i|{
            let cmd=i.modifiers.command;
            (cmd && i.key_pressed(egui::Key::Z) && !i.modifiers.shift,
             (cmd && i.key_pressed(egui::Key::Z) && i.modifiers.shift)
                || (cmd && i.key_pressed(egui::Key::Y)),
             cmd && i.key_pressed(egui::Key::D),
             cmd && i.key_pressed(egui::Key::A),
             i.key_pressed(egui::Key::Delete) || i.key_pressed(egui::Key::Backspace),
             i.key_pressed(egui::Key::Escape),
             i.key_pressed(egui::Key::Enter),
             !cmd && i.key_pressed(egui::Key::V),
             !cmd && i.key_pressed(egui::Key::N),
             !cmd && i.key_pressed(egui::Key::P),
             !cmd && !i.modifiers.shift && i.key_pressed(egui::Key::F),
             !cmd && i.modifiers.shift && i.key_pressed(egui::Key::F),
             cmd && i.key_pressed(egui::Key::N),
             cmd && i.key_pressed(egui::Key::O),
             cmd && i.key_pressed(egui::Key::S),
             !cmd && i.key_pressed(egui::Key::R),
             !cmd && i.key_pressed(egui::Key::C),
             (i.key_pressed(egui::Key::ArrowRight) as i32
                -i.key_pressed(egui::Key::ArrowLeft) as i32,
              i.key_pressed(egui::Key::ArrowUp) as i32
                -i.key_pressed(egui::Key::ArrowDown) as i32),
             i.modifiers.shift)
        });
        if escape{
            if self.active_shape.is_some(){
                self.active_shape=None;
                self.exact_shape_placement=false;
                self.shape_drag_start=None;
                self.shape_drag_delta=None;
                self.status="Drawing tool cancelled".into();
            }else if self.marquee_start.is_some(){
                self.marquee_start=None;
                self.status="Selection box cancelled".into();
            }else if self.drag.is_some(){
                self.editor.cancel_drag();
                self.drag=None;
                self.status="Drag cancelled · original geometry restored".into();
            }else if self.edit_mode==EditMode::Draw{
                self.drawing.clear();
                self.edit_mode=EditMode::Objects;
            }else{
                self.select_vector(None,false);
            }
            return;
        }
        if new{self.request_document(PendingDocument::New);}
        if open{self.choose_open_document();}
        if save{self.save_command();}
        if undo{self.editor.undo();self.reconcile_selection();}
        if redo{self.editor.redo();self.reconcile_selection();}
        if duplicate{self.duplicate_selection();}
        if select_all{
            self.selected_ids=self.editor.project.paths.iter().filter(|p|p.visible)
                .map(|p|p.id).chain(self.editor.project.contours.iter()
                .filter(|p|p.visible).map(|p|p.id)).collect();
            self.selected_path=None;self.selected=None;
            self.reconcile_selection();
            self.edit_mode=EditMode::Objects;
        }
        if delete{self.delete_selection();}
        if enter && self.edit_mode==EditMode::Draw{self.finish_drawing();}
        if v{self.edit_mode=EditMode::Objects;self.active_shape=None;self.exact_shape_placement=false;self.shape_drag_start=None;self.shape_drag_delta=None;}
        if n{self.edit_mode=EditMode::Nodes;self.active_shape=None;self.shape_drag_start=None;self.shape_drag_delta=None;}
        if p{self.edit_mode=EditMode::Draw;self.active_shape=None;
            self.shape_drag_start=None;self.shape_drag_delta=None;self.drawing.clear();}
        if arrows!=(0,0) && !self.selected_ids.is_empty()
            && self.edit_mode==EditMode::Objects
            && self.active_shape.is_none(){
            let step=self.nudge_mm*if coarse{10.0}else{1.0};
            self.move_selection(Point::new(arrows.0 as f64*step,
                arrows.1 as f64*step));
        }
        if r{self.choose_shape_tool(ShapeKind::Rectangle);}
        if c{self.choose_shape_tool(ShapeKind::Circle);}
        if fit{self.zoom=1.0;self.pan=Vec2::ZERO;}
        if fit_selected{self.fit_selection();}
    }

}
impl eframe::App for Studio {
    fn ui(&mut self,ui:&mut egui::Ui,_frame:&mut eframe::Frame){
        self.keyboard(ui);
        self.show_shell(ui);
    }
}
fn main()->eframe::Result{
    let options=eframe::NativeOptions {
        viewport:egui::ViewportBuilder::default()
            .with_title("CarveFoundry — Vector Design Studio")
            .with_inner_size([1500.,900.])
            .with_min_inner_size([1060.,680.]),
        renderer:eframe::Renderer::Glow,
        ..Default::default()
    };
    eframe::run_native(
        "io.github.newnetmp3.carvefoundry",
        options,
        Box::new(|ctx|{
            ui::theme::install(&ctx.egui_ctx);
            Ok(Box::new(Studio::default()))
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selecting_a_shape_is_not_a_project_edit_and_cancel_is_safe(){
        let mut studio=Studio::default();
        let before=studio.editor.project.clone();
        studio.choose_shape_tool(ShapeKind::Rectangle);
        assert_eq!(studio.active_shape,Some(ShapeKind::Rectangle));
        assert_eq!(studio.editor.project,before);
        studio.active_shape=None;
        studio.exact_shape_placement=false;
        studio.shape_drag_start=None;
        assert_eq!(studio.editor.project,before);
        assert!(!studio.editor.can_undo());
    }

    #[test]
    fn completed_shape_gesture_creates_one_undoable_vector(){
        let mut studio=Studio::default();
        studio.choose_shape_tool(ShapeKind::Ellipse);
        let original=studio.editor.project.clone();
        let place=carvefoundry_core::shape_placement(
            Point::new(22.5,13.0),Point::new(50.0,25.0),
            ShapeKind::Ellipse,false).unwrap();
        studio.create_drag_shape(ShapeKind::Ellipse,place);
        assert_eq!(studio.editor.project.paths.len(),1);
        assert_eq!(studio.editor.project.paths[0].origin,place.origin);
        assert_eq!(studio.selected_path,Some(1));
        assert_eq!(studio.active_shape,Some(ShapeKind::Ellipse));
        assert!(studio.editor.undo());
        assert_eq!(studio.editor.project,original);
        assert!(!studio.editor.can_undo());
    }

    #[test]
    fn exact_shape_position_mode_is_non_mutating_until_placed() {
        let mut studio=Studio::default();
        let original=studio.editor.project.clone();
        studio.choose_exact_shape_placement(ShapeKind::Rectangle);
        assert!(studio.exact_shape_placement);
        assert_eq!(studio.editor.project,original);
        let desired=carvefoundry_core::ShapePlacement{
            origin:Point::new(37.5,18.25),
            width_mm:studio.shape_width,
            height_mm:studio.shape_height,
        };
        studio.create_drag_shape(ShapeKind::Rectangle,desired);
        assert_eq!(studio.editor.project.paths[0].origin,desired.origin);
        assert!(studio.editor.undo());
        assert_eq!(studio.editor.project,original);
    }

    #[test]
    fn additive_selection_toggles_without_changing_design(){
        let mut studio=Studio::default();
        studio.add_shape(ShapeKind::Rectangle);
        studio.add_shape(ShapeKind::Ellipse);
        let baseline=studio.editor.project.clone();
        studio.select_vector(Some(1),false);
        studio.select_vector(Some(2),true);
        assert_eq!(studio.selected_ids.len(),2);
        studio.select_vector(Some(2),true);
        assert_eq!(studio.selected_ids.iter().copied().collect::<Vec<_>>(),vec![1]);
        studio.select_vector(None,false);
        assert!(studio.selected_ids.is_empty());
        assert_eq!(studio.editor.project,baseline);
    }
    #[test]
    fn selection_camera_fit_changes_view_not_project(){
        let mut studio=Studio::default();
        studio.add_shape(ShapeKind::Rectangle);
        let original=studio.editor.project.clone();
        studio.fit_selection();
        assert_eq!(studio.editor.project,original);
        assert!(studio.zoom.is_finite() && studio.zoom>=0.25 && studio.zoom<=8.0);
        assert!(studio.pan.x.is_finite()&&studio.pan.y.is_finite());
    }
    #[test]
    fn exact_multi_vector_move_is_a_single_history_step(){
        let mut studio=Studio::default();
        studio.add_shape(ShapeKind::Rectangle);
        studio.add_shape(ShapeKind::Ellipse);
        studio.selected_ids=[1,2].into_iter().collect();
        studio.reconcile_selection();
        let baseline=studio.editor.project.clone();
        studio.move_selection(Point::new(12.5,-3.75));
        assert_eq!(studio.editor.project.paths[0].origin,
            baseline.paths[0].origin.offset(12.5,-3.75));
        assert_eq!(studio.editor.project.paths[1].origin,
            baseline.paths[1].origin.offset(12.5,-3.75));
        assert!(studio.editor.undo());
        assert_eq!(studio.editor.project,baseline);
    }
    #[test]
    fn dirty_design_requires_confirmation_before_new(){
        let mut studio=Studio::default();
        studio.add_shape(ShapeKind::Rectangle);
        assert_ne!(studio.editor.project,studio.saved_project);
        let count=studio.editor.project.paths.len();
        studio.request_document(PendingDocument::New);
        assert_eq!(studio.pending_document,Some(PendingDocument::New));
        assert_eq!(studio.editor.project.paths.len(),count);
    }

    #[test]
    fn clean_new_document_resets_selection_and_never_marks_saved(){
        let mut studio=Studio::default();
        studio.add_shape(ShapeKind::Star);
        studio.new_document();
        assert!(studio.editor.project.paths.is_empty());
        assert!(studio.selected_id().is_none());
        assert_eq!(studio.workspace,Workspace::Drawing);
        assert!(!studio.has_saved_file);
        assert_eq!(studio.project_path,"untitled.cfd");
        assert_eq!(studio.editor.project,studio.saved_project);
    }

    #[test]
    fn direct_node_and_handle_picks_open_properties_without_editing_geometry(){
        let mut studio=Studio::default();
        studio.add_shape(ShapeKind::Ellipse);
        let before=studio.editor.project.clone();
        let node_id=studio.editor.project.paths[0].nodes[0].id;
        let segment_id=studio.editor.project.paths[0].segments[0].id;

        studio.inspector_tab=InspectorTab::Objects;
        studio.apply_canvas_hit(Some(Hit::Node{path_id:1,node_id}),false);
        assert!(matches!(studio.inspector_tab,InspectorTab::Properties));
        assert_eq!(studio.selected_node,Some(node_id));
        assert_eq!(studio.editor.project,before);

        studio.inspector_tab=InspectorTab::Objects;
        studio.apply_canvas_hit(Some(Hit::Handle{path_id:1,segment_id,handle:1}),false);
        assert!(matches!(studio.inspector_tab,InspectorTab::Properties));
        assert_eq!(studio.selected_handle,Some((segment_id,1)));
        assert_eq!(studio.editor.project,before);
    }

    #[test]
    fn installed_font_can_produce_real_native_analytic_glyphs(){
        let mut studio=Studio::default();
        studio.start_text();
        if studio.font_choices.is_empty(){
            // Headless minimal installations may contain no host fonts.
            return;
        }
        let mut any=false;
        for face in studio.font_database.faces(){
            let Some((family,_))=face.families.first() else{continue;};
            let spec=TextSpec{
                text:"O".into(),family:family.clone(),
                postscript:face.post_script_name.clone(),
                height_mm:20.0,tracking_mm:0.0,
                origin:Point::new(20.0,25.0),
            };
            if let Some(Ok(paths))=studio.font_database.with_face_data(face.id,
                |bytes,index|carvefoundry_core::outline_text(bytes,index,&spec))
                && paths.iter().any(|p|p.segments.iter().any(
                    |s|matches!(s.curve,carvefoundry_core::Curve::Cubic{..}))){
                assert!(paths.iter().all(|p|p.validate().is_ok()));
                any=true;
                break;
            }
        }
        assert!(any,"No installed font could outline a basic rounded glyph");
    }
    #[test]
    fn svg_import_is_one_undo_and_failed_import_is_non_mutating(){
        let mut studio=Studio::default();
        let empty=studio.editor.project.clone();
        let svg=br#"<svg width="300mm" height="200mm"><path d="M 10 10 L 20 20"/></svg>"#;
        studio.import_svg_bytes(svg).unwrap();
        assert_eq!(studio.editor.project.paths.len(),1);
        assert_eq!(studio.selected_ids.len(),1);
        assert_eq!(studio.inspector_tab,InspectorTab::Objects);
        let imported=studio.editor.project.clone();
        assert!(studio.import_svg_bytes(br#"<svg><rect/></svg>"#).is_err());
        assert_eq!(studio.editor.project,imported);
        assert!(studio.editor.undo());
        assert_eq!(studio.editor.project,empty);
    }
    #[test]
    fn dxf_import_is_one_undoable_operation_and_invalid_data_is_atomic(){
        let mut studio=Studio::default();
        studio.add_shape(ShapeKind::Rectangle);
        let before=studio.editor.project.clone();
        let dxf=carvefoundry_core::export_dxf(&before).unwrap();
        let n=studio.import_dxf_bytes(dxf.as_bytes()).unwrap();
        assert_eq!(n,1);
        assert_eq!(studio.selected_ids.len(),1);
        assert_eq!(studio.editor.project.paths.len(),2);
        let imported=studio.editor.project.clone();
        assert!(studio.import_dxf_bytes(b"0\nEOF\n").is_err());
        assert_eq!(studio.editor.project,imported);
        assert!(studio.editor.undo());
        assert_eq!(studio.editor.project,before);
    }
    #[test]
    fn switching_workspaces_cannot_generate_nc_or_mutate_design(){
        let mut studio=Studio::default();
        studio.add_shape(ShapeKind::Ellipse);
        let original=studio.editor.project.clone();
        studio.workspace=Workspace::Toolpaths;
        assert_eq!(studio.editor.project,original);
        studio.workspace=Workspace::Drawing;
        assert_eq!(studio.editor.project,original);
    }
}
