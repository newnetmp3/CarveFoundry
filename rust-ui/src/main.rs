//! Rust-native workspace and panels. The separate layout format never pretends
//! to be a CF3D project and SVG export contains no machine instructions.
use carvefoundry_studio::arrays::array_selected;
use carvefoundry_studio::cam_readout::CamReadout;
use carvefoundry_studio::geometry::{Part, Sheet, area, ellipse, polygon, rectangle, star};
use carvefoundry_studio::nesting::{contains, nest};
use carvefoundry_studio::multi_sheet::{nest_multiple, MultiSheetPlan, NestSettings};
use std::sync::mpsc::{self, Receiver, TryRecvError};
use std::time::Duration;
use carvefoundry_studio::svg;
use carvefoundry_studio::source_placement::SourcePlacement;
use std::io::Write;
use std::process::{Command, Stdio};
use carvefoundry_studio::plan_io::{deserialize_plan, serialize_plan};
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
    cf3d_path: String,
    cf3d_output_path: String,
    source_link: Option<SourcePlacement>,
    cam_readout: Option<CamReadout>,
    cam_readout_path: String,
    inspecting_cam: Option<Receiver<(String, Result<CamReadout, String>)>>,
    cam_template_path: String,
    cam_template_output: String,
    cam_template_operation_id: String,
    cam_template_job: Option<Receiver<(String, Result<String, String>)>>,
    svg_path: String,
    zoom: f32,
    message: String,
    dragging: bool,
    plan: Option<MultiSheetPlan>,
    plan_index: usize,
    planning: Option<Receiver<Result<MultiSheetPlan, String>>>,
    nest_max_sheets: usize,
    nest_allow_rotation: bool,
    plan_path: String,
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
            cf3d_path: "project.cf3d".into(),
            cf3d_output_path: "project-rust-placement.cf3d".into(),
            source_link: None,
            cam_readout: None,
            cam_readout_path: String::new(),
            inspecting_cam: None,
            cam_template_path: "carvefoundry-cam-settings.json".into(),
            cam_template_output: "job-with-template.cf3d".into(),
            cam_template_operation_id: String::new(),
            cam_template_job: None,
            svg_path: "carvefoundry-layout.svg".into(),
            zoom: 1.0,
            message: "Ready · Stock XY0 is bottom-left · Layout only; no G-code".into(),
            dragging: false,
            plan: None,
            plan_index: 0,
            planning: None,
            nest_max_sheets: 8,
            nest_allow_rotation: true,
            plan_path: "carvefoundry-multi-plan.json".into(),
        }
    }
}

impl Studio {
    fn remember(&mut self) {
        self.plan = None;
        self.planning = None;
        self.plan_index = 0;
        self.undo.push(self.sheet.clone());
        if self.undo.len() > 48 { self.undo.remove(0); }
        self.redo.clear();
    }
    fn undo(&mut self) {
        self.plan = None;
        self.planning = None;
        self.plan_index = 0;
        if let Some(previous) = self.undo.pop() {
            self.redo.push(std::mem::replace(&mut self.sheet, previous));
            self.message = "Reverted previous layout edit".into();
        }
    }
    fn redo(&mut self) {
        self.plan = None;
        self.planning = None;
        self.plan_index = 0;
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
    fn start_multi_nest(&mut self) {
        if self.planning.is_some() {
            return;
        }
        let settings = NestSettings {
            gap_mm: self.nest_gap,
            margin_mm: self.stock_margin,
            step_mm: self.search_step,
            allow_quarter_turns: self.nest_allow_rotation,
            max_sheets: self.nest_max_sheets,
        };
        if let Err(error) = settings.validate() {
            self.message = error;
            return;
        }
        let source = self.sheet.clone();
        let (sender, receiver) = mpsc::channel();
        std::thread::spawn(move || {
            let _ = sender.send(nest_multiple(&source, settings));
        });
        self.plan = None;
        self.planning = Some(receiver);
        self.plan_index = 0;
        self.message = "Calculating multi-sheet layout on a worker thread…".into();
    }
    fn poll_multi_nest(&mut self, ui: &egui::Ui) {
        let outcome = self.planning.as_ref().map(|receiver| receiver.try_recv());
        match outcome {
            Some(Ok(Ok(plan))) => {
                self.message = format!(
                    "{} sheets arranged from {} source parts; inspect each sheet before CAM",
                    plan.sheets.len(), self.sheet.parts.len()
                );
                self.plan = Some(plan);
                self.planning = None;
                self.plan_index = 0;
                self.selected = None;
            }
            Some(Ok(Err(error))) => {
                self.message = format!("Multi-sheet nesting rejected: {error}");
                self.planning = None;
            }
            Some(Err(TryRecvError::Disconnected)) => {
                self.message = "Multi-sheet planning worker failed; source layout unchanged".into();
                self.planning = None;
            }
            Some(Err(TryRecvError::Empty)) => {
                ui.ctx().request_repaint_after(Duration::from_millis(60));
            }
            None => {}
        }
    }
    fn save_multi_plan(&mut self) {
        let Some(plan) = &self.plan else { return };
        let result = serialize_plan(plan).and_then(|data| {
            std::fs::write(&self.plan_path, data).map_err(|e| e.to_string())
        });
        self.message = match result {
            Ok(()) => format!("Saved read-only multi-sheet plan to {}", self.plan_path),
            Err(error) => format!("Multi-sheet plan save rejected: {error}"),
        };
    }
    fn load_multi_plan(&mut self) {
        // Read-only plan preview. This is never a source CF3D project load.
        let source = std::path::Path::new(&self.plan_path);
        let parsed = std::fs::metadata(source)
            .map_err(|e| e.to_string())
            .and_then(|metadata| {
                if metadata.len() > 8 * 1024 * 1024 {
                    Err("Multi-sheet plan file exceeds the 8 MiB limit".to_owned())
                } else {
                    std::fs::read_to_string(source).map_err(|e| e.to_string())
                }
            })
            .and_then(|content| deserialize_plan(&content));
        match parsed {
            Ok(plan) => {
                self.planning = None;
                self.plan_index = 0;
                self.selected = None;
                self.message = format!(
                    "Opened {}-sheet read-only plan from {}. Original editable vectors unchanged.",
                    plan.sheets.len(), self.plan_path
                );
                self.plan = Some(plan);
            }
            Err(error) => {
                self.message = format!(
                    "Plan file rejected: {error}. Existing source and preview unchanged."
                );
            }
        }
    }
    fn export_multi_svg(&mut self) {
        let Some(plan) = &self.plan else { return };
        if let Err(error) = plan.validate() {
            self.message = format!("Plan export rejected: {error}");
            return;
        }
        let path = std::path::Path::new(&self.svg_path);
        let parent = path.parent().unwrap_or_else(|| std::path::Path::new("."));
        let stem = path.file_stem().unwrap_or_default().to_string_lossy();
        if stem.is_empty() {
            self.message = "Supply an SVG filename for sheet exports".into();
            return;
        }
        // Validate all sheets/contours before writing any SVG files.
        let sources: Result<Vec<String>, String> = plan.sheets.iter().map(svg::export).collect();
        let sources = match sources {
            Ok(svg) => svg,
            Err(error) => {
                self.message = format!("Sheet export rejected: {error}");
                return;
            }
        };
        for (i, data) in sources.iter().enumerate() {
            let output = parent.join(format!("{stem}-sheet-{:02}.svg", i + 1));
            if let Err(error) = std::fs::write(&output, data) {
                self.message = format!(
                    "Export stopped at {}: {error}; previously written SVG files may exist",
                    output.display()
                );
                return;
            }
        }
        self.message = format!(
            "Exported {} SVG sheets (layout contours only, not CNC toolpaths).",
            sources.len()
        );
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
                self.source_link = None;
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
    fn import_cf3d(&mut self) {
        // Deliberately read-only. The Python serializer remains the authority
        // for the native CF3D format; output is an independent layout copy.
        let executable = std::env::var("CARVEFOUNDRY_PYTHON")
            .unwrap_or_else(|_| "python3".into());
        let command = std::process::Command::new(&executable)
            .args([
                "-m", "carvefoundry.core.rust_layout_snapshot",
                self.cf3d_path.as_str(),
            ])
            .output();
        match command {
            Err(error) => {
                self.message = format!("Cannot launch CF3D snapshot bridge: {error}");
            }
            Ok(output) if !output.status.success() => {
                let reason = String::from_utf8_lossy(&output.stderr);
                self.message = format!("CF3D import rejected: {}", reason.trim());
            }
            Ok(output) => {
                let parsed = serde_json::from_slice::<serde_json::Value>(&output.stdout)
                    .map_err(|error| error.to_string())
                    .and_then(|value| {
                        let skipped = value.get("skipped_items").and_then(|v| v.as_u64()).unwrap_or(0);
                        let sheet = serde_json::from_value::<Sheet>(value.clone())
                            .map_err(|error| error.to_string())?;
                        sheet.validate()?;
                        let link = SourcePlacement::from_snapshot(
                            &value, &sheet, &self.cf3d_path,
                        )?;
                        Ok((sheet, skipped, link))
                    });
                match parsed {
                    Ok((sheet, skipped, link)) => {
                        self.remember();
                        self.selected = None;
                        self.sheet = sheet;
                        let path = std::path::Path::new(&self.cf3d_path);
                        if let Some(stem) = path.file_stem() {
                            self.cf3d_output_path = path.with_file_name(
                                format!("{}-rust-placement.cf3d", stem.to_string_lossy())
                            ).to_string_lossy().into_owned();
                        }
                        self.source_link = Some(link);
                        self.message = format!(
                            "Read-only CF3D vector snapshot imported; {skipped} objects skipped. \
                             Optional XY moves may be committed only to a NEW project. \
                             Other geometry and CAM data cannot be edited here.",
                        );
                    }
                    Err(error) => {
                        self.message = format!("CF3D snapshot has invalid geometry or source identity: {error}");
                    }
                }
            }
        }
    }

    fn start_cam_inspection(&mut self) {
        if self.inspecting_cam.is_some() {
            return;
        }
        let source = self.cf3d_path.clone();
        let python = std::env::var("CARVEFOUNDRY_PYTHON")
            .unwrap_or_else(|_| "python3".into());
        let (sender, receiver) = mpsc::channel();
        std::thread::spawn(move || {
            let outcome = Command::new(python)
                .args(["-m", "carvefoundry.core.rust_cam_readout", source.as_str()])
                .output()
                .map_err(|e| e.to_string())
                .and_then(|result| {
                    if result.status.success() {
                        CamReadout::decode(&result.stdout)
                    } else {
                        Err(String::from_utf8_lossy(&result.stderr).trim().to_owned())
                    }
                });
            let _ = sender.send((source, outcome));
        });
        self.cam_readout = None;
        self.cam_readout_path.clear();
        self.inspecting_cam = Some(receiver);
        self.message = "Reading CF3D CAM stage information (no project changes)…".into();
    }

    fn poll_cam_inspection(&mut self, ui: &egui::Ui) {
        let outcome = self.inspecting_cam.as_ref().map(|r| r.try_recv());
        match outcome {
            Some(Ok((source, result))) => {
                self.inspecting_cam = None;
                if source != self.cf3d_path {
                    self.message = "CF3D path changed during inspection; rerun inspection".into();
                    return;
                }
                match result {
                    Ok(report) => {
                        if let Some(link) = &self.source_link
                            && link.source_path == source
                            && link.source_sha256 != report.source_sha256 {
                            self.message = "Source CF3D changed since vector import; reimport before saving placements".into();
                            return;
                        }
                        self.cam_readout_path = source;
                        self.message = format!(
                            "Read-only CAM: {} stage(s), {} require recalculation, {} have no motion; no CNC preflight",
                            report.operation_count, report.counts.stale,
                            report.counts.missing_motion,
                        );
                        self.cam_readout = Some(report);
                    }
                    Err(error) => self.message = format!("CAM inspection rejected: {error}"),
                }
            }
            Some(Err(TryRecvError::Disconnected)) => {
                self.inspecting_cam = None;
                self.message = "CAM inspector stopped without a valid response".into();
            }
            Some(Err(TryRecvError::Empty)) => {
                ui.ctx().request_repaint_after(Duration::from_millis(80));
            }
            None => {}
        }
    }

    fn start_cam_template_job(&mut self, apply: bool) {
        if self.cam_template_job.is_some() { return; }
        let Some(report) = self.cam_readout.as_ref() else {
            self.message = "Inspect the source CF3D CAM operations first".into();
            return;
        };
        if self.cam_readout_path != self.cf3d_path
            || !report.operations.iter().any(|op| op.operation_id == self.cam_template_operation_id) {
            self.message = "Select an inspected operation from the current CF3D first".into();
            return;
        }
        let source = self.cf3d_path.clone();
        let expected = report.source_sha256.clone();
        let op_id = self.cam_template_operation_id.clone();
        let template = self.cam_template_path.clone();
        let output_path = self.cam_template_output.clone();
        let python = std::env::var("CARVEFOUNDRY_PYTHON")
            .unwrap_or_else(|_| "python3".into());
        let (sender, receiver) = mpsc::channel();
        std::thread::spawn(move || {
            let mut command = Command::new(python);
            command.args([
                "-m", "carvefoundry.core.cam_settings_template",
                if apply { "apply" } else { "export" },
                source.as_str(), op_id.as_str(), template.as_str(),
                "--expected-sha", expected.as_str(),
            ]);
            if apply {
                command.args(["--output", output_path.as_str()]);
            }
            let result = command.output().map_err(|e| e.to_string()).and_then(|output| {
                if !output.status.success() {
                    return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
                }
                let report: serde_json::Value = serde_json::from_slice(&output.stdout)
                    .map_err(|e| format!("Template engine returned invalid JSON: {e}"))?;
                if apply {
                    if report["requires_regeneration_and_preflight"] != true
                        || report["template_applied"] != true {
                        return Err("Template engine did not certify CAM invalidation".into());
                    }
                    Ok(format!(
                        "NEW CF3D created: {}. All paths invalidated. Open in verified CAM, regenerate, preflight and export there.",
                        output_path
                    ))
                } else if report["is_gcode"] == false {
                    Ok(format!("Saved reusable settings JSON: {template}. No toolpath or NC motion exported."))
                } else {
                    Err("Template engine returned an unsafe or unknown response".into())
                }
            });
            let _ = sender.send((source, result));
        });
        self.cam_template_job = Some(receiver);
        self.message = if apply {
            "Applying CAM settings to a NEW CF3D; original stays unchanged…".into()
        } else { "Exporting a reusable CAM settings template…".into() };
    }

    fn poll_cam_template_job(&mut self, ui: &egui::Ui) {
        let response = self.cam_template_job.as_ref().map(|r| r.try_recv());
        match response {
            Some(Ok((source, outcome))) => {
                self.cam_template_job = None;
                self.message = if source == self.cf3d_path {
                    match outcome {
                        Ok(message) => message,
                        Err(error) => format!("CAM template rejected: {error}"),
                    }
                } else {
                    "Source path changed while template operation was running; inspect output in verified CAM".into()
                };
            }
            Some(Err(TryRecvError::Disconnected)) => {
                self.cam_template_job = None;
                self.message = "CAM template process stopped without confirmation".into();
            }
            Some(Err(TryRecvError::Empty)) => {
                ui.ctx().request_repaint_after(Duration::from_millis(80));
            }
            None => {}
        }
    }

    fn save_cf3d_placements(&mut self) {
        let Some(link) = &self.source_link else {
            self.message = "Import a source CF3D project before requesting a placement transaction".into();
            return;
        };
        if self.plan.is_some() || self.planning.is_some() {
            self.message = "Close the multi-sheet preview before saving CF3D vector placements".into();
            return;
        }
        let payload = match link.request(&self.sheet) {
            Ok(value) => value,
            Err(error) => {
                self.message = format!("CF3D placement blocked: {error}");
                return;
            }
        };
        let executable = std::env::var("CARVEFOUNDRY_PYTHON")
            .unwrap_or_else(|_| "python3".into());
        let mut process = match Command::new(&executable)
            .args([
                "-m", "carvefoundry.core.rust_project_transaction",
                "apply", link.source_path.as_str(), self.cf3d_output_path.as_str(),
            ])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(process) => process,
            Err(error) => {
                self.message = format!("Cannot launch guarded CF3D writer: {error}");
                return;
            }
        };
        let request_bytes = serde_json::to_vec(&payload).unwrap_or_default();
        let write_result = process.stdin.take().ok_or("Missing writer input")
            .and_then(|mut input| input.write_all(&request_bytes).map_err(|_| "Could not send writer request"));
        if let Err(error) = write_result {
            self.message = error.to_owned();
            let _ = process.wait();
            return;
        }
        match process.wait_with_output() {
            Ok(output) if output.status.success() => {
                let parsed: Result<serde_json::Value, _> = serde_json::from_slice(&output.stdout);
                match parsed {
                    Ok(report) if report["requires_cam_regeneration_and_preflight"] == true => {
                        self.message = format!(
                            "Created NEW {}. Prior generated toolpaths removed; \
                            open it in verified CAM, regenerate all toolpaths and repeat preflight.",
                            self.cf3d_output_path,
                        );
                    }
                    _ => {
                        self.message = "Writer finished but did not confirm CAM invalidation; inspect output in verified CAM".into();
                    }
                }
            }
            Ok(output) => {
                self.message = format!(
                    "CF3D placement rejected: {}",
                    String::from_utf8_lossy(&output.stderr).trim()
                );
            }
            Err(error) => {
                self.message = format!("Could not complete CF3D placement: {error}");
            }
        }
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
                self.source_link = None;
            }
            if ui.button("Undo").clicked() { self.undo(); }
            if ui.button("Redo").clicked() { self.redo(); }
            ui.separator();
            ui.label("Layout file:");
            ui.add(egui::TextEdit::singleline(&mut self.layout_path).desired_width(185.0));
            if ui.button("Open").clicked() { self.load(); }
            if ui.button("Save").clicked() { self.save(); }
            ui.separator();
            ui.label("Existing CF3D:");
            ui.add(egui::TextEdit::singleline(&mut self.cf3d_path).desired_width(155.0));
            if ui.button("Import vectors (read-only)").clicked() { self.import_cf3d(); }
            if ui.add_enabled(
                self.inspecting_cam.is_none(),
                egui::Button::new(if self.inspecting_cam.is_some() {
                    "Inspecting CAM…" } else { "Inspect CAM (read-only)" }),
            ).clicked() { self.start_cam_inspection(); }
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
        ui.heading("MULTI-SHEET NESTING");
        ui.small("First-fit stock sheets; no CNC tools or fixtures are transferred.");
        ui.horizontal(|ui| {
            ui.label("Max sheets");
            ui.add(egui::DragValue::new(&mut self.nest_max_sheets).range(1..=32));
        });
        ui.checkbox(&mut self.nest_allow_rotation, "Allow 90° rotation (disable to preserve grain)");
        if ui.add_enabled(self.planning.is_none(), egui::Button::new(
            if self.planning.is_some() { "Nesting…" } else { "Arrange across sheets" }
        )).clicked() { self.start_multi_nest(); }
        ui.label("Plan JSON filename");
        ui.text_edit_singleline(&mut self.plan_path);
        if ui.button("Open saved plan (read-only)").clicked() { self.load_multi_plan(); }
        if let Some(plan) = &self.plan {
            ui.strong(format!("{} sheets in current plan", plan.sheets.len()));
            ui.horizontal(|ui| {
                ui.label("Sheet");
                if ui.small_button("◀").clicked() {
                    self.plan_index = self.plan_index.saturating_sub(1);
                }
                ui.label(format!("{} / {}", self.plan_index + 1, plan.sheets.len()));
                if ui.small_button("▶").clicked() {
                    self.plan_index = (self.plan_index + 1).min(plan.sheets.len() - 1);
                }
            });
            if ui.button("Save multi-sheet plan").clicked() { self.save_multi_plan(); }
            ui.label("SVG output filename prefix");
            ui.text_edit_singleline(&mut self.svg_path);
            if ui.button("Export SVG for every sheet").clicked() { self.export_multi_svg(); }
            if ui.button("Back to editable design").clicked() {
                self.plan = None;
                self.plan_index = 0;
                self.message = "Back to source design. Multi-sheet preview closed.".into();
            }
        }
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
        if let Some(report) = &self.cam_readout
            && self.cam_readout_path == self.cf3d_path {
            ui.separator();
            ui.heading("CF3D CAM STATUS");
            ui.colored_label(Color32::YELLOW, "INSPECTION ONLY · NO PREFLIGHT");
            ui.label(format!(
                "{} stages · {} saved toolpaths · {} fixtures",
                report.operation_count, report.generated_toolpath_count,
                report.fixture_count
            ));
            ui.label(format!(
                "Stale: {}  Missing: {}  Disabled: {}",
                report.counts.stale, report.counts.missing_motion, report.counts.disabled
            ));
            ui.label(format!(
                "Stored motion (unverified): {}", report.counts.motion_present_unverified
            ));
            let mut chosen_template_stage = None;
            egui::ScrollArea::vertical().max_height(230.0).show(ui, |ui| {
                for stage in &report.operations {
                    ui.group(|ui| {
                        ui.strong(format!("{} · {}", stage.strategy, stage.state.label()));
                        ui.label(format!("{} · {:.2} mm", stage.cutter_name, stage.cutter_diameter_mm));
                        ui.small(format!(
                            "{} linked sources · {} saved paths · {} moves",
                            stage.source_item_count, stage.generated_toolpath_count,
                            stage.motion_move_count,
                        ));
                        if let Some(reason) = &stage.stale_reason {
                            ui.colored_label(Color32::YELLOW, reason);
                        }
                        if ui.small_button("Use operation for settings template").clicked() {
                            chosen_template_stage = Some(stage.operation_id.clone());
                        }
                    });
                }
            });
            if let Some(id) = chosen_template_stage {
                self.cam_template_operation_id = id;
            }
            ui.small("Read-only state; all CNC export requires verified CAM and current preflight.");
            ui.separator();
            ui.heading("REUSABLE CAM SETTINGS");
            ui.small("Settings only: same operation strategy, identical cutter geometry and parameter schema required.");
            ui.label(format!(
                "Selected operation UUID: {}",
                if self.cam_template_operation_id.is_empty() {
                    "None"
                } else { self.cam_template_operation_id.as_str() }
            ));
            ui.label("Template JSON path:");
            ui.text_edit_singleline(&mut self.cam_template_path);
            ui.label("New project output (.cf3d):");
            ui.text_edit_singleline(&mut self.cam_template_output);
            let can_run = self.cam_template_job.is_none()
                && !self.cam_template_operation_id.is_empty();
            if ui.add_enabled(can_run, egui::Button::new("Export operation settings")).clicked() {
                self.start_cam_template_job(false);
            }
            if ui.add_enabled(can_run, egui::Button::new("Apply template to NEW CF3D")).clicked() {
                self.start_cam_template_job(true);
            }
            ui.small("Template application removes saved motion, marks every CAM stage stale and NEVER exports G-code.");
        }
        if let Some(source) = &self.source_link {
            ui.separator();
            ui.strong("CF3D PROJECT PLACEMENT");
            ui.small("Supported: XY motion only, saved to a NEW native project. Rotation, shape, name, Z, toolpaths and fixtures cannot be edited here.");
            ui.label(format!("Source: {}", source.source_path));
            ui.label("New CF3D output path:");
            ui.text_edit_singleline(&mut self.cf3d_output_path);
            if ui.button("Save XY placements as NEW CF3D").clicked() {
                self.save_cf3d_placements();
            }
            ui.small("All previous toolpaths are removed and CAM operations marked stale. Reopen the new project in verified CAM and run preflight.");
        }
        if let Some(plan) = &self.plan
            && let Some(sheet) = plan.sheets.get(self.plan_index) {
            ui.heading(format!("Sheet {} of {}", self.plan_index + 1, plan.sheets.len()));
            ui.strong("READ-ONLY MULTI-SHEET PREVIEW");
            ui.label(format!("{} × {} mm", sheet.width_mm, sheet.height_mm));
            ui.label(format!("{} parts", sheet.parts.len()));
            if let Some(used) = plan.utilization_percent(self.plan_index) {
                ui.label(format!("{used:.1}% nominal outline area (excludes kerf)"));
            }
            ui.separator();
            for part in &sheet.parts { ui.label(&part.name); }
            ui.separator();
            ui.small("Return to editable design before changing stock or vectors. Export every sheet separately as SVG, then validate all operations in verified CAM.");
            return;
        }
        let stock_before = (self.sheet.width_mm, self.sheet.height_mm);
        ui.horizontal(|ui| {
            ui.label("Width");
            ui.add(egui::DragValue::new(&mut self.sheet.width_mm).range(1.0..=100000.0).suffix(" mm"));
        });
        ui.horizontal(|ui| {
            ui.label("Height");
            ui.add(egui::DragValue::new(&mut self.sheet.height_mm).range(1.0..=100000.0).suffix(" mm"));
        });
        if stock_before != (self.sheet.width_mm, self.sheet.height_mm) {
            self.planning = None;
            self.plan = None;
        }
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
        let preview = self.plan.as_ref()
            .and_then(|plan| plan.sheets.get(self.plan_index));
        let sheet = preview.unwrap_or(&self.sheet);
        ui.horizontal(|ui| {
            ui.heading("2D DESIGN");
            ui.separator();
            ui.label(format!("{} × {} mm  ·  {} objects{}", sheet.width_mm, sheet.height_mm, sheet.parts.len(), if preview.is_some() { " · MULTI-SHEET PREVIEW" } else { "" }));
            ui.add(egui::Slider::new(&mut self.zoom, 0.45..=2.8).text("Zoom"));
        });
        let size = ui.available_size().max(Vec2::splat(150.0));
        let (frame, response) = ui.allocate_exact_size(size, Sense::click_and_drag());
        let painter = ui.painter_at(frame);
        painter.rect_filled(frame, 0.0, Color32::from_rgb(18, 23, 32));
        let stock_w = sheet.width_mm.max(1.0);
        let stock_h = sheet.height_mm.max(1.0);
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
        for part in &sheet.parts {
            let selected = preview.is_none() && Some(part.id) == self.selected;
            let pts: Vec<Pos2> = part.world_points().into_iter().map(&screen).collect();
            let edge = if selected { Color32::from_rgb(255, 197, 88) }
                else { Color32::from_rgb(106, 222, 179) };
            painter.add(egui::Shape::closed_line(pts, Stroke::new(if selected { 2.5 } else { 1.5 }, edge)));
        }
        painter.text(screen([0.0, 0.0]) + Vec2::new(5.0, 5.0), egui::Align2::LEFT_TOP, "XY0",
            egui::FontId::monospace(12.0), Color32::from_rgb(189, 222, 236));
        if preview.is_some() {
            return; // No accidental moving parts inside read-only plan preview.
        }
        let mouse = response.interact_pointer_pos();
        let to_world = |pointer: Pos2| -> [f64; 2] {
            [(pointer.x - origin.x) as f64 / scale as f64,
            (origin.y - pointer.y) as f64 / scale as f64]
        };
        if response.clicked() && let Some(pointer) = mouse {
            let world = to_world(pointer);
            self.selected = self.sheet.parts.iter().rev()
                .find(|p| contains(&p.world_points(), world)).map(|p| p.id);
        }
        if response.drag_started() && let Some(pointer) = mouse {
            let world = to_world(pointer);
            self.selected = self.sheet.parts.iter().rev()
                .find(|p| contains(&p.world_points(), world)).map(|p| p.id);
            if self.selected.is_some() {
                self.remember();
                self.dragging = true;
            }
        }
        if self.dragging && response.dragged()
            && let Some(id) = self.selected {
            let delta = ui.input(|input| input.pointer.delta());
            if let Some(part) = self.sheet.parts.iter_mut().find(|p| p.id == id) {
                part.x += delta.x as f64 / scale as f64;
                part.y -= delta.y as f64 / scale as f64;
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
        self.poll_multi_nest(ui);
        self.poll_cam_inspection(ui);
        self.poll_cam_template_job(ui);
        egui::Panel::top("studio-toolbar").show(ui, |ui| {
            self.header(ui);
        });
        egui::Panel::bottom("studio-status").show(ui, |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.label(egui::RichText::new("LAYOUT-ONLY").color(Color32::YELLOW).strong());
                ui.label(&self.message);
                ui.separator();
                let area_mm2: f64 = self.sheet.parts.iter().map(|p| area(&p.outline)).sum();
                ui.weak(format!("Nominal area: {:.1}% of sheet", area_mm2 / (self.sheet.width_mm * self.sheet.height_mm) * 100.0));
            });
        });
        egui::Panel::left("studio-tools").resizable(true).default_size(250.0).min_size(205.0)
            .show(ui, |ui| { egui::ScrollArea::vertical().show(ui, |ui| self.tools(ui)); });
        egui::Panel::right("studio-properties").resizable(true).default_size(260.0).min_size(220.0)
            .show(ui, |ui| { egui::ScrollArea::vertical().show(ui, |ui| self.properties(ui)); });
        egui::CentralPanel::default().show(ui, |ui| self.canvas(ui));
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
