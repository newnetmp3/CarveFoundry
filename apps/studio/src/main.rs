//! CarveFoundry reboot: an independent, 100% Rust desktop and project model.
//! This version cannot generate toolpaths, preflight machine motion or post NC.
use carvefoundry_core::{
    Action, Curve, Editor, Fixture, Hit, PickMode, Point, Primitive, Project,
    ShapeKind, movement_delta, pick,
};
use eframe::egui;
use egui::{Color32, Pos2, Sense, Stroke, Vec2};
use std::path::Path;

#[derive(Clone, Copy, PartialEq, Eq)]
enum EditMode { Objects, Nodes, Draw }
#[derive(Clone, Copy)]
enum ActiveDrag {
    None,
    Contour(u64,Point),
    Path(u64,Point),
    Node(u64,u64,Point),
    Control(u64,u64,u8,Point),
}
struct Studio {
    editor: Editor,
    project_path: String,
    selected: Option<u64>,
    selected_path: Option<u64>,
    selected_node: Option<u64>,
    selected_handle: Option<(u64,u8)>,
    edit_mode: EditMode,
    shape_name: String,
    shape_width: f64,
    shape_height: f64,
    zoom: f32,
    grid_step: f64,
    use_grid: bool,
    drag: Option<ActiveDrag>,
    drawing: Vec<Point>,
    draw_closed: bool,
    status: String,
}
impl Default for Studio {
    fn default() -> Self {
        Self {
            editor: Editor::default(),
            project_path: "carvefoundry-design.cfd".into(),
            selected: None,
            selected_path: None,
            selected_node: None,
            selected_handle: None,
            edit_mode: EditMode::Objects,
            shape_name: "New contour".into(),
            shape_width: 50.0, shape_height: 30.0,
            zoom: 1.0, grid_step: 1.0, use_grid: true,
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
        self.selected = None;
        self.selected_path = None;
        self.selected_node = None;
        self.selected_handle = None;
        self.drag = None;
        self.drawing.clear();
        self.status = "New independent Rust design · No legacy CF3D converter".into();
    }
    fn open_document(&mut self) {
        match Project::open(Path::new(&self.project_path))
            .and_then(Editor::new) {
            Ok(editor) => {
                self.editor = editor;
                self.selected = None;
                self.selected_path = None;
                self.selected_node = None;
                self.selected_handle = None;
                self.drag = None;
                self.drawing.clear();
                self.status = "Opened native Rust design; CNC machining not implemented".into();
            }
            Err(error) => self.status = format!("Open rejected; original design kept: {error}"),
        }
    }
    fn save_document(&mut self) {
        self.status = match self.editor.project.save(Path::new(&self.project_path)) {
            Ok(()) => format!("Saved native Rust design to {}",self.project_path),
            Err(error) => format!("Save failed: {error}"),
        };
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
            self.selected_path=Some(id);self.selected=None;
            self.selected_node=None;self.selected_handle=None;
            self.edit_mode=EditMode::Objects;
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
            self.selected_path=Some(id);self.selected=None;
            self.selected_node=None;self.selected_handle=None;
            self.edit_mode=EditMode::Nodes;
        }else {
            self.drawing=points;
        }
    }
    fn run_selected(&mut self,action:impl FnOnce(u64)->Action){
        if let Some(id)=self.selected_id(){self.apply(action(id));}
        else{self.status="Select a shape first".into();}
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
            self.selected=None;
            self.selected_path=Some(id);
            self.selected_node=Some(1);
            self.selected_handle=None;
            self.edit_mode=EditMode::Nodes;
        }
    }
    fn header(&mut self,ui:&mut egui::Ui) {
        ui.horizontal_wrapped(|ui|{
            ui.heading("CARVEFOUNDRY");
            ui.weak("RUST REBOOT  /  DESIGN");
            ui.separator();
            if ui.button("New").clicked(){self.new_document();}
            if ui.button("Open .cfd").clicked(){self.open_document();}
            if ui.button("Save .cfd").clicked(){self.save_document();}
            ui.add(egui::TextEdit::singleline(&mut self.project_path)
                .desired_width(230.0));
            ui.separator();
            if ui.add_enabled(self.editor.can_undo(),egui::Button::new("Undo")).clicked() {
                self.editor.undo();
            }
            if ui.add_enabled(self.editor.can_redo(),egui::Button::new("Redo")).clicked() {
                self.editor.redo();
            }
            ui.separator();
            ui.colored_label(Color32::from_rgb(244,186,91),
                "DESIGN-ONLY · NO NC OUTPUT");
        });
    }
    fn tools(&mut self,ui:&mut egui::Ui) {
        ui.heading("DESIGN TOOLS");
        ui.small("All geometry, history and file operations run natively in Rust.");
        ui.separator();
        ui.strong("DRAW / CREATE");
        ui.label("Name");
        ui.text_edit_singleline(&mut self.shape_name);
        ui.horizontal(|ui|{
            ui.label("Width");
            ui.add(egui::DragValue::new(&mut self.shape_width)
                .range(0.1..=10_000.0).suffix(" mm"));
        });
        ui.horizontal(|ui|{
            ui.label("Height");
            ui.add(egui::DragValue::new(&mut self.shape_height)
                .range(0.1..=10_000.0).suffix(" mm"));
        });
        ui.label("Basic shapes");
        ui.horizontal_wrapped(|ui|{
            if ui.button("▭ Rectangle").clicked(){self.add_shape(ShapeKind::Rectangle);}
            if ui.button("◯ Circle").clicked(){self.add_shape(ShapeKind::Circle);}
            if ui.button("⬭ Ellipse").clicked(){self.add_shape(ShapeKind::Ellipse);}
        });
        ui.horizontal_wrapped(|ui|{
            if ui.button("△ Triangle").clicked(){self.add_shape(ShapeKind::Triangle);}
            if ui.button("Pentagon").clicked(){self.add_shape(ShapeKind::Pentagon);}
            if ui.button("Hexagon").clicked(){self.add_shape(ShapeKind::Hexagon);}
            if ui.button("Octagon").clicked(){self.add_shape(ShapeKind::Octagon);}
            if ui.button("☆ Star").clicked(){self.add_shape(ShapeKind::Star);}
        });
        if ui.button("✎ Draw polyline / polygon").clicked(){
            self.edit_mode=EditMode::Draw;
            self.drawing.clear();
            self.selected_node=None;self.selected_handle=None;
        }
        if self.edit_mode==EditMode::Draw {
            ui.checkbox(&mut self.draw_closed,"Close outline into polygon");
            ui.label(format!("{} points · click canvas to add",self.drawing.len()));
            ui.horizontal(|ui|{
                if ui.add_enabled(self.drawing.len()>=if self.draw_closed{3}else{2},
                    egui::Button::new("Finish ↵")).clicked(){self.finish_drawing();}
                if ui.button("Cancel Esc").clicked(){
                    self.drawing.clear();self.edit_mode=EditMode::Objects;
                }
            });
            ui.small("Click each point on stock · Enter/double-click finishes · Escape cancels. Grid snap optional.");
        }
        ui.separator();
        ui.strong("ADD RETAINED ANALYTIC PATH");
        ui.horizontal_wrapped(|ui|{
            if ui.button("Line").clicked(){self.add_analytic(Primitive::Line);}
            if ui.button("Circular arc").clicked(){self.add_analytic(Primitive::Arc);}
            if ui.button("Cubic Bézier").clicked(){self.add_analytic(Primitive::Cubic);}
        });
        ui.small("Line/arc/cubic remain mathematical segments in .cfd. The displayed linework is preview-only.");
        ui.separator();
        ui.heading("EDIT MODE");
        ui.horizontal_wrapped(|ui|{
            ui.selectable_value(&mut self.edit_mode,EditMode::Objects,"V · Select");
            ui.selectable_value(&mut self.edit_mode,EditMode::Nodes,"N · Nodes");
            ui.selectable_value(&mut self.edit_mode,EditMode::Draw,"P · Pen");
        });
        ui.small("Object mode translates complete contours/paths. Node mode edits anchors and cubic handles without flattening curves.");
        ui.separator();
        ui.heading("POSITION");
        ui.checkbox(&mut self.use_grid,"Snap drag delta to grid");
        ui.horizontal(|ui|{
            ui.label("Grid");
            ui.add(egui::DragValue::new(&mut self.grid_step)
                .range(0.1..=100.0).suffix(" mm"));
        });
        ui.small("First click-drag an anchor/handle directly. Drags start at mouse-down position. Grid snaps movement only and never jumps the node to grid.");
        ui.separator();
        ui.heading("EDIT OPERATIONS");
        ui.horizontal_wrapped(|ui|{
            if ui.button("Duplicate · Ctrl+D").clicked(){
                self.run_selected(|id|Action::Duplicate{id});
            }
            if ui.button("Flip X").clicked(){
                self.run_selected(|id|Action::Flip{id,horizontal:true});
            }
            if ui.button("Flip Y").clicked(){
                self.run_selected(|id|Action::Flip{id,horizontal:false});
            }
        });
        ui.horizontal_wrapped(|ui|{
            if ui.button("Center X").clicked(){
                self.run_selected(|id|Action::Center{id,horizontal:true,vertical:false});
            }
            if ui.button("Center Y").clicked(){
                self.run_selected(|id|Action::Center{id,horizontal:false,vertical:true});
            }
            if ui.button("Center both").clicked(){
                self.run_selected(|id|Action::Center{id,horizontal:true,vertical:true});
            }
        });
        ui.horizontal(|ui|{
            if ui.button("Show").clicked(){
                self.run_selected(|id|Action::SetVisible{id,visible:true});
            }
            if ui.button("Hide").clicked(){
                self.run_selected(|id|Action::SetVisible{id,visible:false});
            }
        });
        ui.small("Ctrl+Z Undo · Ctrl+Shift+Z/Ctrl+Y Redo · Delete removes selection · Escape cancels drag · F fits view.");
        ui.label("• True 3D mesh viewport");
        ui.label("• Native machining operations");
        ui.label("• Fixture-aware CAM safety");
        ui.small("There is no Python dependency or legacy project import in this reboot.");
    }
    fn properties(&mut self,ui:&mut egui::Ui) {
        ui.heading("PROJECT");
        ui.strong(&self.editor.project.name);
        ui.small("Project renaming will be added with undoable project commands.");
        ui.separator();
        ui.heading("STOCK");
        ui.label("XY0 bottom-left · Z0 stock top");
        let mut stock=self.editor.project.stock.clone();
        let mut changed=false;
        ui.horizontal(|ui|{
            ui.label("Width");
            changed|=ui.add(egui::DragValue::new(&mut stock.width_mm)
                .range(1.0..=100_000.).suffix(" mm")).changed();
        });
        ui.horizontal(|ui|{
            ui.label("Height");
            changed|=ui.add(egui::DragValue::new(&mut stock.height_mm)
                .range(1.0..=100_000.).suffix(" mm")).changed();
        });
        ui.horizontal(|ui|{
            ui.label("Thickness");
            changed|=ui.add(egui::DragValue::new(&mut stock.thickness_mm)
                .range(0.1..=100_000.).suffix(" mm")).changed();
        });
        if changed {self.apply(Action::ChangeStock(stock));}
        ui.separator();
        ui.heading("FIXTURE INVENTORY");
        ui.small("Visualization only · cutter/holder clearance not yet checked.");
        for fixture in &self.editor.project.fixtures {
            ui.group(|ui|{
                ui.strong(&fixture.name);
                ui.label(format!("X {:.1}..{:.1} · Y {:.1}..{:.1} mm",
                    fixture.min.x,fixture.max.x,fixture.min.y,fixture.max.y));
                ui.label(format!("Top relative Z {:.1} mm · margin {:.1} mm",
                    fixture.top_z_mm,fixture.clearance_mm));
            });
        }
        if ui.button("Add sample left fence").clicked() {
            let height=self.editor.project.stock.height_mm;
            let top_z=23.-self.editor.project.stock.thickness_mm;
            self.apply(Action::AddFixture(Fixture {
                name:format!("Left fence {}",self.editor.project.fixtures.len()+1),
                min:Point::new(-10.,0.),max:Point::new(0.,height),
                top_z_mm:top_z,clearance_mm:2.,
            }));
        }
        ui.small("Sample assumes a fence 23 mm above the bed. Adjust real dimensions in a future fixture editor before CAM.");
        ui.separator();
        ui.heading("CONTOURS");
        egui::ScrollArea::vertical().max_height(150.0).show(ui,|ui|{
            for contour in &self.editor.project.contours {
                let label=format!("{}{}",
                    if contour.locked{"🔒 "}else{""},contour.name);
                ui.selectable_value(&mut self.selected,Some(contour.id),label);
            }
        });
        let selected=self.editor.project.contours.iter()
            .find(|p|Some(p.id)==self.selected).cloned();
        if let Some(contour)=selected {
            ui.separator();
            ui.strong(format!("EDIT · {}",contour.name));
            ui.small(format!("Stable part ID {}",contour.id));
            let mut x=contour.origin.x;
            let mut y=contour.origin.y;
            let mut moved=false;
            ui.horizontal(|ui|{
                ui.label("X");
                moved|=ui.add(egui::DragValue::new(&mut x).speed(0.25)
                    .suffix(" mm")).changed();
                ui.label("Y");
                moved|=ui.add(egui::DragValue::new(&mut y).speed(0.25)
                    .suffix(" mm")).changed();
            });
            if moved{self.apply(Action::Move{id:contour.id,origin:Point::new(x,y)});}
            let mut locked=contour.locked;
            if ui.checkbox(&mut locked,"Lock contour").changed(){
                self.apply(Action::SetLocked{id:contour.id,locked});
            }
            if ui.add_enabled(!contour.locked,
                egui::Button::new("Delete selected contour")).clicked(){
                self.apply(Action::Remove{id:contour.id});
                self.selected=None;
            }
        }
        ui.separator();
        ui.heading("ANALYTIC VECTORS");
        let prior=self.selected_path;
        egui::ScrollArea::vertical().max_height(120.0).show(ui,|ui|{
            for path in &self.editor.project.paths {
                ui.selectable_value(&mut self.selected_path,Some(path.id),format!(
                    "{}{} · {} segment(s)",
                    if path.locked {"🔒 "} else {""},
                    path.name,path.segments.len(),
                ));
            }
        });
        if self.selected_path!=prior {
            self.selected=None;
            self.selected_node=None;
            self.selected_handle=None;
        }
        let selected_path=self.editor.project.paths.iter()
            .find(|p|Some(p.id)==self.selected_path).cloned();
        if let Some(path)=selected_path {
            ui.separator();
            ui.strong(format!("RETAINED PATH · {}",path.name));
            ui.small(format!("Stable path ID {} · {} nodes · {} curves",
                path.id,path.nodes.len(),path.segments.len()));
            let mut origin=path.origin;
            let mut moved=false;
            ui.horizontal(|ui|{
                ui.label("X");
                moved|=ui.add(egui::DragValue::new(&mut origin.x)
                    .speed(0.25).suffix(" mm")).changed();
                ui.label("Y");
                moved|=ui.add(egui::DragValue::new(&mut origin.y)
                    .speed(0.25).suffix(" mm")).changed();
            });
            if moved{self.apply(Action::MovePath{id:path.id,origin});}
            let mut locked=path.locked;
            if ui.checkbox(&mut locked,"Lock analytic path").changed(){
                self.apply(Action::SetPathLocked{id:path.id,locked});
            }
            ui.horizontal(|ui|{
                if ui.add_enabled(!locked,egui::Button::new(
                    if path.closed{"Open path"}else{"Close with line"}
                )).clicked(){
                    self.apply(Action::SetPathClosed{id:path.id,closed:!path.closed});
                }
                if ui.add_enabled(!locked,egui::Button::new("Delete path")).clicked(){
                    self.apply(Action::RemovePath{id:path.id});
                    self.selected_path=None;
                    self.selected_node=None;
                    self.selected_handle=None;
                }
            });
            ui.small("Closing requires 3+ noncollinear nodes. Never silently converts curves to polylines.");
            ui.separator();
            ui.label("Path nodes · local coordinates");
            for node in &path.nodes {
                ui.selectable_value(&mut self.selected_node,Some(node.id),
                    format!("#{} · {:.2}, {:.2} mm",
                        node.id,node.position.x,node.position.y));
            }
            if let Some(node)=path.nodes.iter().find(|n|Some(n.id)==self.selected_node) {
                ui.strong(format!("NODE #{}",node.id));
                let mut at=node.position;
                let mut changed=false;
                ui.horizontal(|ui|{
                    ui.label("X");
                    changed|=ui.add(egui::DragValue::new(&mut at.x)
                        .speed(0.1).suffix(" mm")).changed();
                    ui.label("Y");
                    changed|=ui.add(egui::DragValue::new(&mut at.y)
                        .speed(0.1).suffix(" mm")).changed();
                });
                if changed{self.apply(Action::MoveNode{
                    path_id:path.id,node_id:node.id,position:at,
                });}
                ui.horizontal_wrapped(|ui|{
                    if ui.add_enabled(!locked,
                        egui::Button::new("Insert midpoint after node")).clicked(){
                        let new_id=path.next_element_id;
                        self.apply(Action::InsertNodeAfter{
                            path_id:path.id,node_id:node.id,
                        });
                        if self.editor.project.paths.iter()
                            .any(|p|p.id==path.id &&
                                p.nodes.iter().any(|n|n.id==new_id)){
                            self.selected_node=Some(new_id);
                        }
                    }
                    if ui.add_enabled(!locked,
                        egui::Button::new("Delete node")).clicked(){
                        self.apply(Action::RemoveNode{
                            path_id:path.id,node_id:node.id,
                        });
                        self.selected_node=None;
                    }
                });
                ui.small("Arc anchors are fixed until radius-constrained node editing is implemented. Cubic controls move with their anchors.");
            }
            ui.separator();
            ui.label("Cubic control handles");
            for seg in &path.segments {
                if let Curve::Cubic{control1,control2} = seg.curve {
                    ui.horizontal(|ui|{
                        ui.selectable_value(&mut self.selected_handle,
                            Some((seg.id,1)),format!("Segment #{} · H1",seg.id));
                        ui.selectable_value(&mut self.selected_handle,
                            Some((seg.id,2)),format!("H2 ({:.1}, {:.1})",
                                control2.x,control2.y));
                    });
                    if self.selected_handle==Some((seg.id,1)) ||
                        self.selected_handle==Some((seg.id,2)) {
                        let handle=self.selected_handle.unwrap().1;
                        let mut value=if handle==1{control1}else{control2};
                        let mut changed=false;
                        ui.horizontal(|ui|{
                            ui.label("X");
                            changed|=ui.add(egui::DragValue::new(&mut value.x)
                                .speed(0.1).suffix(" mm")).changed();
                            ui.label("Y");
                            changed|=ui.add(egui::DragValue::new(&mut value.y)
                                .speed(0.1).suffix(" mm")).changed();
                        });
                        if changed{self.apply(Action::MoveControl{
                            path_id:path.id,segment_id:seg.id,handle,position:value,
                        });}
                    }
                }
            }
            ui.small("Selections, node moves and handles are serialized losslessly into .cfd, with undoable modifications.");
        }
        ui.separator();
        ui.heading("MACHINING");
        ui.colored_label(Color32::YELLOW,
            "Not implemented · no toolpaths, preflight or G-code");
        for msg in self.editor.project.design_warnings(){
            ui.colored_label(Color32::from_rgb(244,186,91),msg);
        }
    }
    fn canvas(&mut self,ui:&mut egui::Ui) {
        ui.horizontal(|ui|{
            ui.heading("STOCK / VECTOR DESIGN");
            ui.separator();
            ui.label(format!("{} contours · {} analytic paths · {:.0}×{:.0} mm",
                self.editor.project.contours.len(),self.editor.project.paths.len(),
                self.editor.project.stock.width_mm,
                self.editor.project.stock.height_mm));
            ui.add(egui::Slider::new(&mut self.zoom,0.4..=4.0).text("Zoom"));
        });
        let size=ui.available_size().max(Vec2::splat(150.0));
        let (rect,response)=ui.allocate_exact_size(size,Sense::click_and_drag());
        let painter=ui.painter_at(rect);
        painter.rect_filled(rect,0.0,Color32::from_rgb(18,23,32));
        let stock=&self.editor.project.stock;
        let scale=(((size.x-60.0)/stock.width_mm as f32)
            .min((size.y-60.0)/stock.height_mm as f32)).max(0.0001)*self.zoom;
        let origin=Pos2::new(
            rect.center().x-stock.width_mm as f32*scale*0.5,
            rect.center().y+stock.height_mm as f32*scale*0.5,
        );
        let screen=|p:Point|Pos2::new(
            origin.x+p.x as f32*scale,
            origin.y-p.y as f32*scale,
        );
        let back=egui::Rect::from_two_pos(screen(Point::new(0.,0.)),
            screen(Point::new(stock.width_mm,stock.height_mm)));
        painter.rect_filled(back,0.0,Color32::from_rgb(41,55,68));
        painter.rect_stroke(back,0.0,
            Stroke::new(2.,Color32::from_rgb(121,176,202)),
            egui::StrokeKind::Inside);
        if scale>2.0 {
            for x in (0..=stock.width_mm as usize).step_by(10){
                painter.line_segment([screen(Point::new(x as f64,0.)),
                    screen(Point::new(x as f64,stock.height_mm))],
                    Stroke::new(0.5,Color32::from_gray(65)));
            }
            for y in (0..=stock.height_mm as usize).step_by(10){
                painter.line_segment([screen(Point::new(0.,y as f64)),
                    screen(Point::new(stock.width_mm,y as f64))],
                    Stroke::new(0.5,Color32::from_gray(65)));
            }
        }
        for fixture in &self.editor.project.fixtures {
            painter.rect_stroke(
                egui::Rect::from_two_pos(screen(fixture.min),screen(fixture.max)),
                0.0,Stroke::new(2.0,Color32::from_rgb(240,105,105)),
                egui::StrokeKind::Inside,
            );
        }
        for part in &self.editor.project.contours {
            if !part.visible{continue;}
            let points=part.world_points().into_iter().map(&screen).collect();
            let chosen=Some(part.id)==self.selected;
            painter.add(egui::Shape::closed_line(points,
                Stroke::new(if chosen{2.5}else{1.5},
                    if chosen{Color32::from_rgb(255,205,95)}
                    else{Color32::from_rgb(110,222,172)})));
        }
        for path in &self.editor.project.paths {
            if !path.visible {continue;}
            let Ok(polyline)=path.preview_points(0.3) else {continue;};
            let chosen=self.selected_path==Some(path.id);
            let style=Stroke::new(if chosen{2.6}else{1.6},
                if chosen{Color32::from_rgb(255,208,99)}
                else{Color32::from_rgb(124,168,255)});
            let points:Vec<Pos2>=polyline.into_iter().map(&screen).collect();
            if path.closed {painter.add(egui::Shape::closed_line(points,style));}
            else{painter.add(egui::Shape::line(points,style));}
            if chosen && self.edit_mode==EditMode::Nodes {
                for (i,node) in path.nodes.iter().enumerate() {
                    let at=screen(node.position.offset(path.origin.x,path.origin.y));
                    painter.circle_filled(at,if Some(node.id)==self.selected_node{6.5}else{4.5},
                        if Some(node.id)==self.selected_node{Color32::WHITE}
                        else{Color32::from_rgb(255,193,88)});
                    painter.text(at+Vec2::new(6.0,-6.0),egui::Align2::LEFT_BOTTOM,
                        format!("{}",node.id),egui::FontId::monospace(10.0),
                        Color32::from_rgb(255,235,186));
                    if let Some(segment)=path.segments.get(i){
                        match segment.curve {
                            Curve::Cubic{control1,control2} => {
                                let start=node.position.offset(path.origin.x,path.origin.y);
                                let end=path.nodes[(i+1)%path.nodes.len()]
                                    .position.offset(path.origin.x,path.origin.y);
                                for (control,from,handle) in [
                                    (control1,start,1_u8),(control2,end,2_u8),
                                ] {
                                    let world=control.offset(path.origin.x,path.origin.y);
                                    let pos=screen(world);
                                    painter.line_segment([screen(from),pos],
                                        Stroke::new(0.8,Color32::from_rgb(150,167,196)));
                                    painter.circle_filled(pos,
                                        if self.selected_handle==Some((segment.id,handle)){6.0}else{4.0},
                                        Color32::from_rgb(255,130,174));
                                }
                            }
                            Curve::Arc{center,..} => {
                                painter.circle_stroke(
                                    screen(center.offset(path.origin.x,path.origin.y)),
                                    3.0,Stroke::new(1.0,Color32::from_rgb(140,153,180)));
                            }
                            Curve::Line=>{}
                        }
                    }
                }
            }
        }
        painter.text(screen(Point::new(0.,0.))+Vec2::new(6.,6.),
            egui::Align2::LEFT_TOP,"XY0",
            egui::FontId::monospace(12.),Color32::WHITE);
        let pointer=response.interact_pointer_pos();
        let to_world=|p:Pos2|Point::new(
            (p.x-origin.x) as f64/scale as f64,
            (origin.y-p.y) as f64/scale as f64,
        );
        // Read the hit candidates first; mutations below only use stable IDs.
        let radius=10.0/scale as f64;
        let point=pointer.map(to_world);
        let contour_hit=point.and_then(|world|
            self.editor.project.contours.iter().rev().find(|p|
                p.visible && polygon_contains(&p.world_points(),world)).map(|p|p.id));
        let analytic_hit=point.and_then(|world|
            self.editor.project.paths.iter().rev().find(|p|
                path_hit(p,world,radius)).map(|p|p.id));
        let active_path=self.editor.project.paths.iter()
            .find(|p|Some(p.id)==self.selected_path && p.visible);
        let node_hit=if self.edit_mode==EditMode::Nodes {
            point.and_then(|world|active_path.and_then(|path|
                path.nodes.iter().filter(|n|
                    point_distance(n.position.offset(path.origin.x,path.origin.y),world)<radius)
                .min_by(|a,b|{
                    let da=point_distance(a.position.offset(path.origin.x,path.origin.y),world);
                    let db=point_distance(b.position.offset(path.origin.x,path.origin.y),world);
                    da.total_cmp(&db)
                }).map(|n|n.id)))
        } else {None};
        let control_hit=if self.edit_mode==EditMode::Nodes {
            point.and_then(|world|active_path.and_then(|path|
                path.segments.iter().flat_map(|seg|{
                    let mut controls=Vec::new();
                    if let Curve::Cubic{control1,control2}=seg.curve {
                        controls.push((seg.id,1_u8,control1));
                        controls.push((seg.id,2_u8,control2));
                    }
                    controls
                }).filter(|(_,_,at)|point_distance(
                    at.offset(path.origin.x,path.origin.y),world)<radius)
                .min_by(|(_,_,a),(_,_,b)|{
                    let da=point_distance(a.offset(path.origin.x,path.origin.y),world);
                    let db=point_distance(b.offset(path.origin.x,path.origin.y),world);
                    da.total_cmp(&db)
                }).map(|(segment,handle,_)|(segment,handle))))
        } else {None};

        if response.clicked() {
            if self.edit_mode==EditMode::Nodes {
                if let Some(node)=node_hit {
                    self.selected_node=Some(node);
                    self.selected_handle=None;
                }else if let Some((segment,handle))=control_hit {
                    self.selected_handle=Some((segment,handle));
                    self.selected_node=None;
                }else{
                    self.selected_path=analytic_hit;
                    self.selected_node=None;
                    self.selected_handle=None;
                    self.selected=None;
                }
            }else{
                self.selected_path=analytic_hit;
                self.selected=if analytic_hit.is_some(){None}else{contour_hit};
                self.selected_node=None;
                self.selected_handle=None;
            }
        }
        if response.drag_started() {
            let started=if self.edit_mode==EditMode::Nodes {
                if let (Some(path_id),Some(node_id))=(self.selected_path,node_hit) {
                    self.selected_node=Some(node_id);
                    self.selected_handle=None;
                    self.editor.start_node_drag(path_id,node_id)
                        .map(|pos|ActiveDrag::Node(path_id,node_id,pos))
                }else if let (Some(path_id),Some((segment,handle)))=
                    (self.selected_path,control_hit) {
                    self.selected_node=None;
                    self.selected_handle=Some((segment,handle));
                    self.editor.start_control_drag(path_id,segment,handle)
                        .map(|pos|ActiveDrag::Control(path_id,segment,handle,pos))
                }else {
                    self.selected_path=analytic_hit;
                    self.selected_node=None;
                    self.selected_handle=None;
                    Ok(ActiveDrag::None)
                }
            }else if let Some(id)=analytic_hit {
                self.selected_path=Some(id);
                self.selected=None;
                self.editor.start_path_drag(id).map(|p|ActiveDrag::Path(id,p))
            }else if let Some(id)=contour_hit {
                self.selected=Some(id);
                self.selected_path=None;
                self.editor.start_drag(id).map(|p|ActiveDrag::Contour(id,p))
            }else {
                self.selected=None;
                self.selected_path=None;
                Ok(ActiveDrag::None)
            };
            match started {
                Ok(ActiveDrag::None)=>self.drag=None,
                Ok(other)=>self.drag=Some(other),
                Err(reason)=>self.status=format!("Drag refused: {reason}"),
            }
        }
        if response.dragged() && let Some(target)=self.drag {
            let pixels=response.drag_delta();
            let (path_origin,start)=match target {
                ActiveDrag::Contour(_,p)|ActiveDrag::Path(_,p)=>(Point::new(0.0,0.0),p),
                ActiveDrag::Node(path_id,_,p)|ActiveDrag::Control(path_id,_,_,p)=>{
                    let at=self.editor.project.paths.iter().find(|v|v.id==path_id)
                        .map(|v|v.origin).unwrap_or(Point::new(0.0,0.0));
                    (at,p)
                }
                ActiveDrag::None=>(Point::new(0.0,0.0),Point::new(0.0,0.0)),
            };
            let mut next=start.offset(
                pixels.x as f64/scale as f64,
                -pixels.y as f64/scale as f64,
            );
            if self.use_grid && self.grid_step.is_finite()
                && (0.1..=100.0).contains(&self.grid_step) {
                next.x=((next.x+path_origin.x)/self.grid_step).round()
                    *self.grid_step-path_origin.x;
                next.y=((next.y+path_origin.y)/self.grid_step).round()
                    *self.grid_step-path_origin.y;
            }
            let result=match target {
                ActiveDrag::Contour(id,_)=>self.editor.preview_drag(id,next),
                ActiveDrag::Path(id,_)=>self.editor.preview_path_drag(id,next),
                ActiveDrag::Node(id,node,_)=>self.editor.preview_node_drag(id,node,next),
                ActiveDrag::Control(id,seg,handle,_)=>
                    self.editor.preview_control_drag(id,seg,handle,next),
                ActiveDrag::None=>Ok(()),
            };
            if let Err(reason)=result {self.status=format!("Drag rejected: {reason}");}
        }
        if response.drag_stopped() {
            self.editor.finish_drag();
            self.drag=None;
        }
        if let Some(cursor)=response.hover_pos() {
            let world=to_world(cursor);
            painter.text(rect.right_bottom()-Vec2::new(12.,12.),
                egui::Align2::RIGHT_BOTTOM,
                format!("X {:.2} · Y {:.2} mm",world.x,world.y),
                egui::FontId::monospace(12.),Color32::WHITE);
        }
    }
}
impl eframe::App for Studio {
    fn ui(&mut self,ui:&mut egui::Ui,_frame:&mut eframe::Frame){
        egui::Panel::top("top").show(ui,|ui|self.header(ui));
        egui::Panel::bottom("status").show(ui,|ui|{
            ui.horizontal_wrapped(|ui|{
                ui.colored_label(Color32::YELLOW,"RUST CAD · CNC DISABLED");
                ui.label(&self.status);
            });
        });
        egui::Panel::left("design-tools").resizable(true)
            .default_size(240.).min_size(200.).show(ui,|ui|{
                egui::ScrollArea::vertical().show(ui,|ui|self.tools(ui));
            });
        egui::Panel::right("inspector").resizable(true)
            .default_size(290.).min_size(230.).show(ui,|ui|{
                egui::ScrollArea::vertical().show(ui,|ui|self.properties(ui));
            });
        egui::CentralPanel::default().show(ui,|ui|self.canvas(ui));
    }
}
fn main()->eframe::Result{
    let options=eframe::NativeOptions {
        viewport:egui::ViewportBuilder::default()
            .with_title("CarveFoundry · Pure Rust Reboot")
            .with_inner_size([1500.,900.])
            .with_min_inner_size([980.,650.]),
        renderer:eframe::Renderer::Glow,
        ..Default::default()
    };
    eframe::run_native(
        "io.github.newnetmp3.carvefoundry",
        options,
        Box::new(|ctx|{
            ctx.egui_ctx.set_theme(egui::Theme::Dark);
            Ok(Box::new(Studio::default()))
        }),
    )
}
