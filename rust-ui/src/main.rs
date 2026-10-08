//! Rust-native workspace and panels. The separate layout format never pretends
//! to be a CF3D project and SVG export contains no machine instructions.
use carvefoundry_studio::arrays::array_selected;
use carvefoundry_studio::geometry::{Part, Sheet, area, ellipse, polygon, rectangle, star};
use carvefoundry_studio::nesting::{contains, nest};
use carvefoundry_studio::svg;
use eframe::egui;
use egui::{Color32, Pos2, Sense, Stroke, Vec2};

#[derive(Clone, Copy, PartialEq)]
enum ShapeTool { Rectangle, Ellipse, Polygon, Star }
impl ShapeTool {
    fn label(self) -> &'static str {
        match self {
            Self::Rectangle => "Rectangle",
            Self::Ellipse => "Ellipse",
            Self::Polygon => "Polygon",
            Self::Star => "Star",
        }
    }
}

struct Studio {
    sheet: Sheet,
    selected: Option<u64>,
    undo: Vec<Sheet>,
    redo: Vec<Sheet>,
    tool: ShapeTool,
    width: f64,
    height: f64,
    sides: usize,
    inner_percent: f64,
    nest_gap: f64,
    stock_margin: f64,
    search_step: f64,
    array_rows: usize,
    array_columns: usize,
    array_gap: f64,
    layout_path: String,
    svg_path: String,
    zoom: f32,
    message: String,
    dragging: bool,
}

impl Default for Studio {
    fn default() -> Self {
        Self {
            sheet: Sheet::default(),
            selected: None,
            undo: vec![],
            redo: vec![],
            tool: ShapeTool::Rectangle,
            width: 50.0,
            height: 30.0,
            sides: 6,
            inner_percent: 45.0,
            nest_gap: 3.0,
            stock_margin: 5.0,
            search_step: 3.0,
            array_rows: 2,
            array_columns: 3,
            array_gap: 5.0,
            layout_path: "carvefoundry-layout.json".into(),
            svg_path: "carvefoundry-layout.svg".into(),
            zoom: 1.0,
            message: "Ready · Stock XY0 is bottom-left · Layout only; no G-code".into(),
            dragging: false,
        }
    }
}

impl Studio {
    fn remember(&mut self) {
        self.undo.push(self.sheet.clone());
        if self.undo.len() > 48 { self.undo.remove(0); }
        self.redo.clear();
    }
    fn undo(&mut self) {
        if let Some(previous) = self.undo.pop() {
            self.redo.push(std::mem::replace(&mut self.sheet, previous));
            self.message = "Reverted previous layout edit".into();
        }
    }
    fn redo(&mut self) {
        if let Some(next) = self.redo.pop() {
            self.undo.push(std::mem::replace(&mut self.sheet, next));
            self.message = "Reapplied layout edit".into();
        }
    }
    fn add(&mut self) {
        if self.sheet.parts.len() >= 512
            || !self.width.is_finite() || !self.height.is_finite()
            || !(0.5..=2000.0).contains(&self.width)
            || !(0.5..=2000.0).contains(&self.height) {
            self.message = "Invalid dimensions or maximum 512 parts reached".into();
            return;
        }
        let outline = match self.tool {
            ShapeTool::Rectangle => rectangle(self.width, self.height),
            ShapeTool::Ellipse => ellipse(self.width, self.height, 72),
            ShapeTool::Polygon => polygon(self.sides.clamp(3, 32), self.width / 2.0),
            ShapeTool::Star => star(
                self.sides.clamp(3, 32),
                self.width / 2.0,
                self.width / 2.0 * (self.inner_percent / 100.0).clamp(0.1, 0.95),
            ),
        };
        self.remember();
        let id = self.sheet.next_id();
        self.sheet.parts.push(Part {
            id,
            name: format!("{} {}", self.tool.label(), id),
            outline, x: self.stock_margin.max(0.0), y: self.stock_margin.max(0.0),
            quarter_turns: 0,
        });
        self.selected = Some(id);
        self.message = format!("Created editable {}", self.tool.label());
    }
    fn duplicate(&mut self) {
        if let Some(part) = self.sheet.parts.iter().find(|p| Some(p.id) == self.selected).cloned() {
            if self.sheet.parts.len() >= 512 { self.message = "Part limit reached".into(); return; }
            self.remember();
            let mut new_part = part;
            new_part.id = self.sheet.next_id();
            new_part.name.push_str(" copy");
            new_part.x += 8.0;
            new_part.y += 8.0;
            self.selected = Some(new_part.id);
            self.sheet.parts.push(new_part);
        }
    }
    fn apply_nest(&mut self) {
        match nest(&self.sheet, self.nest_gap, self.stock_margin, self.search_step) {
            Ok(output) => {
                if output != self.sheet {
                    self.remember();
                    self.sheet = output;
                }
                self.message = "Polygon-aware first-fit layout completed. Verify all offsets before CAM.".into();
            }
            Err(error) => self.message = format!("Layout rejected: {error}"),
        }
    }
    fn apply_array(&mut self) {
        if let Some(id) = self.selected {
            match array_selected(
                &self.sheet, id, self.array_rows, self.array_columns, self.array_gap,
            ) {
                Ok(result) => {
                    if result != self.sheet {
                        self.remember();
                        self.sheet = result;
                    }
                    self.message = "Array added with stock/collision checks".into();
                }
                Err(error) => self.message = format!("Array rejected: {error}"),
            }
        } else {
            self.message = "Select a source part before making an array".into();
        }
    }
    fn save(&mut self) {
        if let Err(error) = self.sheet.validate() {
            self.message = error;
            return;
        }
        let result = serde_json::to_string_pretty(&self.sheet)
            .map_err(|e| e.to_string())
            .and_then(|json| std::fs::write(&self.layout_path, json).map_err(|e| e.to_string()));
        self.message = match result {
            Ok(()) => format!("Saved editable Rust layout: {}", self.layout_path),
            Err(error) => format!("Save rejected: {error}"),
        };
    }
    fn load(&mut self) {
        let result = std::fs::read_to_string(&self.layout_path)
            .map_err(|e| e.to_string())
            .and_then(|content| serde_json::from_str::<Sheet>(&content).map_err(|e| e.to_string()))
            .and_then(|sheet| sheet.validate().map(|_| sheet));
        match result {
            Ok(sheet) => {
                self.remember();
                self.sheet = sheet;
                self.selected = None;
                self.message = "Editable layout loaded; toolpaths are not part of this format".into();
            }
            Err(error) => self.message = format!("Open rejected: {error}"),
        }
    }
    fn export_svg(&mut self) {
        self.message = match svg::export(&self.sheet)
            .and_then(|content| std::fs::write(&self.svg_path, content).map_err(|e| e.to_string())) {
            Ok(()) => format!("Exported vector contours to {}. Import into verified CAM before cutting.", self.svg_path),
            Err(error) => format!("SVG export rejected: {error}"),
        };
    }
    fn open_legacy_cam(&mut self) {
        // Launch, never impersonate the tested Python CAM preflight.
        match std::process::Command::new("carvefoundry").spawn() {
            Ok(_) => self.message = "Opened existing CNC CAM application".into(),
            Err(error) => self.message = format!("Cannot launch CAM ({error}). Use ~/.local/bin/carvefoundry."),
        }
    }
    fn header(&mut self, ui: &mut egui::Ui) {
        ui.horizontal_wrapped(|ui| {
            ui.heading("CARVEFOUNDRY");
            ui.weak("STUDIO  /  RUST NATIVE");
            ui.separator();
            if ui.button("New layout").clicked() {
                self.remember();
                self.sheet = Sheet::default();
                self.selected = None;
            }
            if ui.button("Undo").clicked() { self.undo(); }
            if ui.button("Redo").clicked() { self.redo(); }
            ui.separator();
            ui.label("Layout file:");
            ui.add(egui::TextEdit::singleline(&mut self.layout_path).desired_width(185.0));
            if ui.button("Open").clicked() { self.load(); }
            if ui.button("Save").clicked() { self.save(); }
            ui.separator();
            if ui.button("Open verified CAM ↗").clicked() { self.open_legacy_cam(); }
        });
    }
    fn tools(&mut self, ui: &mut egui::Ui) {
        ui.heading("DRAW / DESIGN");
        ui.label("Native vector geometry");
        ui.separator();
        for option in [ShapeTool::Rectangle, ShapeTool::Ellipse, ShapeTool::Polygon, ShapeTool::Star] {
            ui.selectable_value(&mut self.tool, option, option.label());
        }
        ui.horizontal(|ui| {
            ui.label("Width");
            ui.add(egui::DragValue::new(&mut self.width).range(0.5..=2000.0).speed(0.5).suffix(" mm"));
        });
        ui.horizontal(|ui| {
            ui.label("Height");
            ui.add(egui::DragValue::new(&mut self.height).range(0.5..=2000.0).speed(0.5).suffix(" mm"));
        });
        if matches!(self.tool, ShapeTool::Polygon | ShapeTool::Star) {
            ui.horizontal(|ui| {
                ui.label("Sides / points");
                ui.add(egui::DragValue::new(&mut self.sides).range(3..=32));
            });
        }
        if self.tool == ShapeTool::Star {
            ui.horizontal(|ui| {
                ui.label("Inner radius");
                ui.add(egui::DragValue::new(&mut self.inner_percent).range(10.0..=95.0).suffix("%"));
            });
        }
        if ui.button("＋ Add vector").clicked() { self.add(); }
        ui.separator();
        ui.heading("PRODUCTION LAYOUT");
        ui.strong("Polygon-aware sheet packing");
        ui.small("First-fit heuristic, 0°/90°/180°/270°. Not globally optimal.");
        ui.horizontal(|ui| {
            ui.label("Cutter gap");
            ui.add(egui::DragValue::new(&mut self.nest_gap).range(0.0..=100.0).suffix(" mm"));
        });
        ui.horizontal(|ui| {
            ui.label("Edge margin");
            ui.add(egui::DragValue::new(&mut self.stock_margin).range(0.0..=100.0).suffix(" mm"));
        });
        ui.horizontal(|ui| {
            ui.label("Search step");
            ui.add(egui::DragValue::new(&mut self.search_step).range(0.5..=50.0).suffix(" mm"));
        });
        if ui.button("Arrange all contours").clicked() { self.apply_nest(); }
        ui.separator();
        ui.heading("ARRAY COPY");
        ui.horizontal(|ui| {
            ui.label("Rows");
            ui.add(egui::DragValue::new(&mut self.array_rows).range(1..=32));
        });
        ui.horizontal(|ui| {
            ui.label("Columns");
            ui.add(egui::DragValue::new(&mut self.array_columns).range(1..=32));
        });
        ui.horizontal(|ui| {
            ui.label("Spacing");
            ui.add(egui::DragValue::new(&mut self.array_gap).range(0.0..=100.0).suffix(" mm"));
        });
        if ui.button("Create selected array").clicked() { self.apply_array(); }
    }
    fn properties(&mut self, ui: &mut egui::Ui) {
        ui.heading("JOB SETUP");
        ui.label(egui::RichText::new("Stock XY0: bottom-left").color(Color32::LIGHT_GREEN));
        ui.horizontal(|ui| {
            ui.label("Width");
            ui.add(egui::DragValue::new(&mut self.sheet.width_mm).range(1.0..=100000.0).suffix(" mm"));
        });
        ui.horizontal(|ui| {
            ui.label("Height");
            ui.add(egui::DragValue::new(&mut self.sheet.height_mm).range(1.0..=100000.0).suffix(" mm"));
        });
        ui.separator();
        ui.heading("PARTS");
        egui::ScrollArea::vertical().max_height(190.0).show(ui, |ui| {
            for part in &self.sheet.parts {
                ui.selectable_value(&mut self.selected, Some(part.id), &part.name);
            }
        });
        let selected_idx = self.sheet.parts.iter().position(|p| Some(p.id) == self.selected);
        if let Some(index) = selected_idx {
            ui.separator();
            ui.strong("SELECTED PART");
            let part = &self.sheet.parts[index];
            let (mut name, mut x, mut y, mut turns) = (part.name.clone(), part.x, part.y, part.quarter_turns);
            let mut changed = false;
            changed |= ui.text_edit_singleline(&mut name).changed();
            ui.horizontal(|ui| {
                ui.label("X"); changed |= ui.add(egui::DragValue::new(&mut x).speed(0.5).suffix(" mm")).changed();
                ui.label("Y"); changed |= ui.add(egui::DragValue::new(&mut y).speed(0.5).suffix(" mm")).changed();
            });
            ui.horizontal(|ui| {
                ui.label("Rotation");
                egui::ComboBox::from_id_salt("quarter_turns").selected_text(format!("{}°", turns as usize * 90))
                    .show_ui(ui, |ui| {
                        for angle in 0..4_u8 {
                            changed |= ui.selectable_value(&mut turns, angle, format!("{}°", angle as usize * 90)).changed();
                        }
                    });
            });
            if changed {
                if x.is_finite() && y.is_finite() && name.len() <= 256 {
                    self.remember();
                    let part = &mut self.sheet.parts[index];
                    part.name = name;
                    part.x = x;
                    part.y = y;
                    part.quarter_turns = turns;
                } else {
                    self.message = "Invalid position or name".into();
                }
            }
            ui.horizontal(|ui| {
                if ui.button("Duplicate").clicked() { self.duplicate(); }
                if ui.button("Remove").clicked() {
                    self.remember();
                    self.sheet.parts.remove(index);
                    self.selected = None;
                }
            });
        }
        ui.separator();
        ui.heading("INTERCHANGE");
        ui.label("SVG import to existing CNC workspace");
        ui.add(egui::TextEdit::singleline(&mut self.svg_path).desired_width(220.0));
        if ui.button("Export vector SVG").clicked() { self.export_svg(); }
        ui.small("SVG only; toolpaths, fixtures, cutter radius and CNC preflight are not exported.");
    }
    fn canvas(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.heading("2D DESIGN");
            ui.separator();
            ui.label(format!("{} × {} mm  ·  {} objects", self.sheet.width_mm, self.sheet.height_mm, self.sheet.parts.len()));
            ui.add(egui::Slider::new(&mut self.zoom, 0.45..=2.8).text("Zoom"));
        });
        let size = ui.available_size().max(Vec2::splat(150.0));
        let (frame, response) = ui.allocate_exact_size(size, Sense::click_and_drag());
        let painter = ui.painter_at(frame);
        painter.rect_filled(frame, 0.0, Color32::from_rgb(18, 23, 32));
        let stock_w = self.sheet.width_mm.max(1.0);
        let stock_h = self.sheet.height_mm.max(1.0);
        let fit = ((size.x - 70.0) / stock_w as f32)
            .min((size.y - 70.0) / stock_h as f32).max(0.001);
        let scale = fit * self.zoom;
        let origin = Pos2::new(frame.center().x - stock_w as f32 * scale * 0.5,
            frame.center().y + stock_h as f32 * scale * 0.5);
        let screen = |p: [f64; 2]| Pos2::new(origin.x + p[0] as f32 * scale,
            origin.y - p[1] as f32 * scale);
        let stock_rect = egui::Rect::from_two_pos(screen([0.0, 0.0]), screen([stock_w, stock_h]));
        painter.rect_filled(stock_rect, 0.0, Color32::from_rgb(38, 51, 65));
        painter.rect_stroke(stock_rect, 0.0, Stroke::new(2.0, Color32::from_rgb(101, 156, 190)), egui::StrokeKind::Inside);
        if scale > 1.6 {
            let grid = 10_usize;
            for x in (0..=stock_w as usize).step_by(grid) {
                let a = screen([x as f64, 0.0]);
                let b = screen([x as f64, stock_h]);
                painter.line_segment([a, b], Stroke::new(0.5, Color32::from_gray(61)));
            }
            for y in (0..=stock_h as usize).step_by(grid) {
                let a = screen([0.0, y as f64]);
                let b = screen([stock_w, y as f64]);
                painter.line_segment([a, b], Stroke::new(0.5, Color32::from_gray(61)));
            }
        }
        for part in &self.sheet.parts {
            let selected = Some(part.id) == self.selected;
            let pts: Vec<Pos2> = part.world_points().into_iter().map(&screen).collect();
            let edge = if selected { Color32::from_rgb(255, 197, 88) }
                else { Color32::from_rgb(106, 222, 179) };
            painter.add(egui::Shape::closed_line(pts, Stroke::new(if selected { 2.5 } else { 1.5 }, edge)));
        }
        painter.text(screen([0.0, 0.0]) + Vec2::new(5.0, 5.0), egui::Align2::LEFT_TOP, "XY0",
            egui::FontId::monospace(12.0), Color32::from_rgb(189, 222, 236));
        let mouse = response.interact_pointer_pos();
        let to_world = |pointer: Pos2| -> [f64; 2] {
            [(pointer.x - origin.x) as f64 / scale as f64,
            (origin.y - pointer.y) as f64 / scale as f64]
        };
        if response.clicked() {
            if let Some(pointer) = mouse {
                let world = to_world(pointer);
                self.selected = self.sheet.parts.iter().rev()
                    .find(|p| contains(&p.world_points(), world)).map(|p| p.id);
            }
        }
        if response.drag_started() {
            if let Some(pointer) = mouse {
                let world = to_world(pointer);
                self.selected = self.sheet.parts.iter().rev()
                    .find(|p| contains(&p.world_points(), world)).map(|p| p.id);
                if self.selected.is_some() {
                    self.remember();
                    self.dragging = true;
                }
            }
        }
        if self.dragging && response.dragged() {
            if let Some(id) = self.selected {
                let delta = ui.input(|input| input.pointer.delta());
                if let Some(part) = self.sheet.parts.iter_mut().find(|p| p.id == id) {
                    part.x += delta.x as f64 / scale as f64;
                    part.y -= delta.y as f64 / scale as f64;
                }
            }
        }
        if response.drag_stopped() {
            self.dragging = false;
            self.message = "Moved layout vector · Verify sheet boundary before exporting".into();
        }
        if let Some(pointer) = response.hover_pos() {
            let world = to_world(pointer);
            ui.ctx().set_cursor_icon(egui::CursorIcon::Crosshair);
            painter.text(frame.right_bottom() - Vec2::new(10.0, 12.0),
                egui::Align2::RIGHT_BOTTOM, format!("X {:.1} · Y {:.1} mm", world[0], world[1]),
                egui::FontId::monospace(12.0), Color32::WHITE);
        }
    }
}

impl eframe::App for Studio {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        egui::TopBottomPanel::top("studio-toolbar").show_inside(ui, |ui| {
            self.header(ui);
        });
        egui::TopBottomPanel::bottom("studio-status").show_inside(ui, |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.label(egui::RichText::new("LAYOUT-ONLY").color(Color32::YELLOW).strong());
                ui.label(&self.message);
                ui.separator();
                let area_mm2: f64 = self.sheet.parts.iter().map(|p| area(&p.outline)).sum();
                ui.weak(format!("Nominal area: {:.1}% of sheet", area_mm2 / (self.sheet.width_mm * self.sheet.height_mm) * 100.0));
            });
        });
        egui::SidePanel::left("studio-tools").resizable(true).default_width(250.0).min_width(205.0)
            .show_inside(ui, |ui| { egui::ScrollArea::vertical().show(ui, |ui| self.tools(ui)); });
        egui::SidePanel::right("studio-properties").resizable(true).default_width(260.0).min_width(220.0)
            .show_inside(ui, |ui| { egui::ScrollArea::vertical().show(ui, |ui| self.properties(ui)); });
        egui::CentralPanel::default().show_inside(ui, |ui| self.canvas(ui));
    }
}

fn main() -> eframe::Result {
    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("CarveFoundry Studio · Native Rust Layout")
            .with_inner_size([1440.0, 850.0])
            .with_min_inner_size([950.0, 610.0]),
        renderer: eframe::Renderer::Glow,
        ..Default::default()
    };
    eframe::run_native(
        "io.github.newnetmp3.CarveFoundryStudio",
        native_options,
        Box::new(|ctx| {
            ctx.egui_ctx.set_theme(egui::Theme::Dark);
            Ok(Box::new(Studio::default()))
        }),
    )
}
