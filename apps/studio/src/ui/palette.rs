//! Compact, discoverable CAD drawing tool palette, independent of the canvas.
use super::super::{EditMode,Studio};
use carvefoundry_core::{Action,Primitive,ShapeKind};
use eframe::egui;

fn shape(ui:&mut egui::Ui,label:&str,tip:&str,selected:bool)->bool {
    let button=egui::Button::new(label).fill(if selected{
        egui::Color32::from_rgb(38,108,160)
    }else{
        egui::Color32::from_rgb(49,63,80)
    });
    ui.add_sized([91.0,38.0],button)
        .on_hover_text(tip).clicked()
}
impl Studio {
    pub(crate) fn drawing_palette(&mut self,ui:&mut egui::Ui){
        ui.horizontal(|ui|{
            ui.heading("DRAWING");
            ui.weak("2D vectors");
        });
        if let Some(tool)=self.active_shape {
            ui.group(|ui|{
                ui.strong(format!("{} drawing tool selected",tool.title()));
                ui.label(if self.exact_shape_placement{"Click the stock to position the precise-size vector."}else{"Drag a diagonal on the stock to set the size."});
                ui.small(if self.exact_shape_placement{"Dimensions below · Esc cancels tool"}else{"Hold Shift for equal sides · Esc cancels tool"});
                if ui.button("Exit shape tool [V]").clicked(){
                    self.active_shape=None;
                    self.exact_shape_placement=false;
                    self.shape_drag_start=None;
                }
            });
        }
        ui.label(egui::RichText::new("1  CREATE VECTORS").strong()
            .color(super::theme::ACCENT));
        ui.group(|ui|{
            ui.horizontal_wrapped(|ui|{
                if shape(ui,"▭ Rectangle","Create a 4-node editable rectangle",self.active_shape==Some(ShapeKind::Rectangle)){
                    self.choose_shape_tool(ShapeKind::Rectangle);
                }
                if shape(ui,"◯ Circle","Create a 4-cubic editable circle approximation",self.active_shape==Some(ShapeKind::Circle)){
                    self.choose_shape_tool(ShapeKind::Circle);
                }
                if shape(ui,"⬭ Ellipse","Create a 4-cubic editable ellipse",self.active_shape==Some(ShapeKind::Ellipse)){
                    self.choose_shape_tool(ShapeKind::Ellipse);
                }
                if shape(ui,"△ Triangle","Create a 3-sided closed vector",self.active_shape==Some(ShapeKind::Triangle)){
                    self.choose_shape_tool(ShapeKind::Triangle);
                }
                if shape(ui,"⬡ Hexagon","Create a 6-sided editable vector",self.active_shape==Some(ShapeKind::Hexagon)){
                    self.choose_shape_tool(ShapeKind::Hexagon);
                }
                if shape(ui,"☆ Star","Create a ten-node star outline",self.active_shape==Some(ShapeKind::Star)){
                    self.choose_shape_tool(ShapeKind::Star);
                }
                if shape(ui,"Pentagon","Create a 5-sided outline",self.active_shape==Some(ShapeKind::Pentagon)){
                    self.choose_shape_tool(ShapeKind::Pentagon);
                }
                if shape(ui,"Octagon","Create an 8-sided outline",self.active_shape==Some(ShapeKind::Octagon)){
                    self.choose_shape_tool(ShapeKind::Octagon);
                }
            });
        });
        ui.small("Click a shape tool, then drag its size on the stock. The project changes only when you release.");
        ui.add_space(5.0);
        ui.label(egui::RichText::new("2  DRAW PATHS").strong()
            .color(super::theme::ACCENT));
        ui.group(|ui|{
            ui.horizontal_wrapped(|ui|{
                if shape(ui,"⌁ Polyline [P]","Click vertices on stock; Enter closes the drawing",false){
                    self.edit_mode=EditMode::Draw;
                    self.active_shape=None;
                    self.shape_drag_start=None;
                    self.drawing.clear();
                }
                if shape(ui,"／ Line","Create an editable analytic straight segment",false){
                    self.add_analytic(Primitive::Line);
                }
                if shape(ui,"◠ Arc","Create an exact circular arc with editable ends",false){
                    self.add_analytic(Primitive::Arc);
                }
                if shape(ui,"〰 Bézier","Create an editable cubic Bézier curve",false){
                    self.add_analytic(Primitive::Cubic);
                }
            });
            if self.edit_mode==EditMode::Draw {
                ui.separator();
                ui.checkbox(&mut self.draw_closed,"Close into outline");
                ui.horizontal_wrapped(|ui|{
                    ui.strong(format!("{} vertices",self.drawing.len()));
                    if ui.add_enabled(
                        self.drawing.len()>=if self.draw_closed{3}else{2},
                        egui::Button::new("Finish [Enter]"),
                    ).clicked(){self.finish_drawing();}
                    if ui.button("Cancel [Esc]").clicked(){
                        self.drawing.clear();
                        self.edit_mode=EditMode::Objects;
                    }
                });
                ui.small("Click points in the drawing area. Double-click or press Enter to finish.");
            }
        });
        ui.add_space(5.0);
        egui::CollapsingHeader::new("3  VECTOR DIMENSIONS")
            .default_open(false).show(ui,|ui|{
                ui.label("New object name");
                ui.text_edit_singleline(&mut self.shape_name);
                ui.columns(2,|cols|{
                    cols[0].label("Width (mm)");
                    cols[0].add(egui::DragValue::new(&mut self.shape_width)
                        .range(0.1..=10_000.0).speed(0.5));
                    cols[1].label("Height (mm)");
                    cols[1].add(egui::DragValue::new(&mut self.shape_height)
                        .range(0.1..=10_000.0).speed(0.5));
                });
                ui.weak("For precise placement: enter dimensions, then click the stock position.");
                if let Some(kind)=self.active_shape
                    && ui.button(format!("Use exact size: {} (click stock)",kind.title()))
                        .on_hover_text("Switches to click-to-place mode; no vector is created until you click stock").clicked(){
                    self.choose_exact_shape_placement(kind);
                }
            });
        egui::CollapsingHeader::new("4  ARRANGE & TRANSFORM")
            .default_open(true).show(ui,|ui|{
                let enabled=self.selected_id().is_some();
                let single=self.selected_ids.len()==1;
                if !single && enabled {
                    ui.small("Multi-selection: duplicate from Objects; drag together to move.");
                }
                ui.horizontal_wrapped(|ui|{
                    if ui.add_enabled(single,egui::Button::new("Duplicate"))
                        .on_hover_text("Create an editable copy, offset 8 mm").clicked(){
                        self.run_selected(|id|Action::Duplicate{id});
                    }
                    if ui.add_enabled(single,egui::Button::new("Mirror X"))
                        .on_hover_text("Mirror selected vector horizontally").clicked(){
                        self.run_selected(|id|Action::Flip{id,horizontal:true});
                    }
                    if ui.add_enabled(single,egui::Button::new("Mirror Y"))
                        .on_hover_text("Mirror selected vector vertically").clicked(){
                        self.run_selected(|id|Action::Flip{id,horizontal:false});
                    }
                });
                ui.horizontal_wrapped(|ui|{
                    if ui.add_enabled(single,egui::Button::new("↶ Rotate 90°")).clicked(){
                        self.run_selected(|id|Action::RotateQuarter{id,clockwise:false});
                    }
                    if ui.add_enabled(single,egui::Button::new("↷ Rotate 90°")).clicked(){
                        self.run_selected(|id|Action::RotateQuarter{id,clockwise:true});
                    }
                });
                ui.horizontal_wrapped(|ui|{
                    if ui.add_enabled(single,egui::Button::new("Center X")).clicked(){
                        self.run_selected(|id|Action::Center{id,horizontal:true,vertical:false});
                    }
                    if ui.add_enabled(single,egui::Button::new("Center Y")).clicked(){
                        self.run_selected(|id|Action::Center{id,horizontal:false,vertical:true});
                    }
                    if ui.add_enabled(single,egui::Button::new("Center both")).clicked(){
                        self.run_selected(|id|Action::Center{id,horizontal:true,vertical:true});
                    }
                });
            });
        egui::CollapsingHeader::new("5  PRECISION ALIGN & POSITION")
            .default_open(true).show(ui,|ui|self.precise_tools(ui));
        egui::CollapsingHeader::new("6  VIEW & SNAP")
            .default_open(false).show(ui,|ui|{
                ui.checkbox(&mut self.show_grid,"Show stock grid");
                ui.checkbox(&mut self.use_grid,"Snap movement to grid");
                ui.checkbox(&mut self.snap_features,"Snap endpoints, midpoints, stock corners")
                    .on_hover_text("Snaps Pen points, exact placement, node and handle movements to real vector features. Uses a 10-pixel screen-space tolerance.");
                ui.horizontal(|ui|{
                    ui.label("Spacing");
                    ui.add(egui::DragValue::new(&mut self.grid_step)
                        .range(0.1..=100.0).suffix(" mm"));
                });
                if ui.button("Fit material [F]").clicked(){
                    self.zoom=1.0;self.pan=egui::Vec2::ZERO;
                }
                ui.weak("Geometry snapping is on by default; grid snapping is off. Off-grid start points never jump.");
            });
        ui.add_space(8.0);
        ui.separator();
        ui.small("V Select  •  N Edit nodes  •  P Pen");
        ui.small("Wheel zoom  •  Middle/right drag pan");
        ui.small("Shift-click add  •  Shift-drag box");
        ui.small("Left→right box encloses · Right→left crosses");
        ui.small("Ctrl+D Copy  •  Ctrl+Z Undo");
    }

    pub(crate) fn toolpaths_palette(&mut self,ui:&mut egui::Ui){
        ui.heading("TOOLPATHS");
        ui.label(egui::RichText::new("Not yet available").strong()
            .color(super::theme::ACCENT));
        ui.separator();
        ui.label("This Rust reboot currently edits CNC design geometry only.");
        ui.small("The machining workflow will be activated after the native CAM engine, verified tool database, fixture/holder checks, posted-code preflight and simulation are implemented.");
        ui.separator();
        ui.strong("Planned machining tools");
        for item in ["Profile / cutout","Pocket clearing","V-carving & engraving",
            "3D roughing and finishing","Material simulation",
            "Fixture-aware preflight","Controller-specific NC export"] {
            ui.add_enabled(false,egui::Button::new(item));
        }
        ui.separator();
        ui.colored_label(egui::Color32::YELLOW,
            "NC output is deliberately unavailable.");
    }
}
