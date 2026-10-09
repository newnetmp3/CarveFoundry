//! CarveFoundry reboot: an independent, 100% Rust desktop and project model.
//! This version cannot generate toolpaths, preflight machine motion or post NC.
use carvefoundry_core::{
    Action, Editor, Fixture, Point, Project, polygon_contains,
};
use eframe::egui;
use egui::{Color32, Pos2, Sense, Stroke, Vec2};
use std::path::Path;

struct Studio {
    editor: Editor,
    project_path: String,
    selected: Option<u64>,
    shape_name: String,
    shape_width: f64,
    shape_height: f64,
    zoom: f32,
    grid_step: f64,
    use_grid: bool,
    drag: Option<(u64, Point)>,
    status: String,
}
impl Default for Studio {
    fn default() -> Self {
        Self {
            editor: Editor::default(),
            project_path: "carvefoundry-design.cfd".into(),
            selected: None,
            shape_name: "New contour".into(),
            shape_width: 50.0, shape_height: 30.0,
            zoom: 1.0, grid_step: 1.0, use_grid: true,
            drag: None,
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
        self.drag = None;
        self.status = "New independent Rust design · No legacy CF3D converter".into();
    }
    fn open_document(&mut self) {
        match Project::open(Path::new(&self.project_path))
            .and_then(Editor::new) {
            Ok(editor) => {
                self.editor = editor;
                self.selected = None;
                self.drag = None;
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
    fn add_rectangle(&mut self) {
        let id = self.editor.project.next_id;
        let pos=10.0+(self.editor.project.contours.len()%10) as f64*8.0;
        self.apply(Action::AddRectangle {
            name:self.shape_name.clone(), origin:Point::new(pos,pos),
            width_mm:self.shape_width, height_mm:self.shape_height,
        });
        if self.editor.project.contours.iter().any(|p|p.id==id) {
            self.selected=Some(id);
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
        ui.strong("ADD CLOSED CONTOUR");
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
        if ui.button("＋ Add rectangle").clicked(){self.add_rectangle();}
        ui.separator();
        ui.heading("POSITION");
        ui.checkbox(&mut self.use_grid,"Snap drag to stock XY grid");
        ui.horizontal(|ui|{
            ui.label("Grid");
            ui.add(egui::DragValue::new(&mut self.grid_step)
                .range(0.1..=100.0).suffix(" mm"));
        });
        ui.small("Left/bottom stock corner is work XY0. Drag a selected contour to move it; changes are a single Undo step.");
        ui.separator();
        ui.heading("NEXT MILESTONES");
        ui.label("• Retained lines, arcs and Béziers");
        ui.label("• Direct node/curve editing");
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
            ui.label(format!("{} contours · {:.0}×{:.0} mm",
                self.editor.project.contours.len(),
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
        painter.text(screen(Point::new(0.,0.))+Vec2::new(6.,6.),
            egui::Align2::LEFT_TOP,"XY0",
            egui::FontId::monospace(12.),Color32::WHITE);
        let pointer=response.interact_pointer_pos();
        let to_world=|p:Pos2|Point::new(
            (p.x-origin.x) as f64/scale as f64,
            (origin.y-p.y) as f64/scale as f64,
        );
        let find=|p:Point| {
            self.editor.project.contours.iter().rev()
                .find(|part|part.visible &&
                    polygon_contains(&part.world_points(),p)).map(|part|part.id)
        };
        if response.clicked() && let Some(cursor)=pointer {
            self.selected=find(to_world(cursor));
        }
        if response.drag_started() && let Some(cursor)=pointer {
            self.selected=find(to_world(cursor));
            if let Some(id)=self.selected {
                match self.editor.start_drag(id) {
                    Ok(anchor)=>self.drag=Some((id,anchor)),
                    Err(reason)=>self.status=format!("Drag refused: {reason}"),
                }
            }
        }
        if response.dragged() && let Some((id,start))=self.drag {
                let pixels=response.drag_delta();
                let mut next=start.offset(
                    pixels.x as f64/scale as f64,
                    -pixels.y as f64/scale as f64,
                );
                if self.use_grid && self.grid_step.is_finite()
                    && (0.1..=100.0).contains(&self.grid_step) {
                    next.x=(next.x/self.grid_step).round()*self.grid_step;
                    next.y=(next.y/self.grid_step).round()*self.grid_step;
                }
                if let Err(reason)=self.editor.preview_drag(id,next) {
                    self.status=format!("Drag rejected: {reason}");
                }
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
