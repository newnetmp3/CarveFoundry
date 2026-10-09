//! Native desktop shell: familiar menu, mode ribbon, drawing palette,
//! object tree, material setup and large central sheet workspace.
use super::super::{EditMode,InspectorTab,PendingDocument,Studio,Workspace};
use carvefoundry_core::{Action,Primitive,ShapeKind};
use eframe::egui;

impl Studio {
    pub(crate) fn show_shell(&mut self,ui:&mut egui::Ui){
        egui::Panel::top("menu-bar").show(ui,|ui|{
            ui.horizontal_wrapped(|ui|{
                ui.heading("CarveFoundry");
                ui.separator();
                ui.menu_button("File",|ui|{
                    if ui.button("New design").on_hover_text("Create a fresh .cfd design")
                        .clicked(){
                        self.request_document(PendingDocument::New);
                        ui.close();
                    }
                    if ui.button("Open project").clicked(){
                        self.request_document(PendingDocument::Open);
                        ui.close();
                    }
                    if ui.button("Save project").clicked(){
                        self.save_document();ui.close();
                    }
                    ui.separator();
                    ui.label("Project file (.cfd)");
                    ui.add(egui::TextEdit::singleline(&mut self.project_path)
                        .desired_width(270.0));
                    ui.weak("Open/Save operate on the path above.");
                    ui.separator();
                    ui.small("Projects are Rust-native; historic CF3D files cannot be opened.");
                });
                ui.menu_button("Edit",|ui|{
                    if ui.add_enabled(self.editor.can_undo(),
                        egui::Button::new("Undo  Ctrl+Z")).clicked(){
                        self.editor.undo();ui.close();
                    }
                    if ui.add_enabled(self.editor.can_redo(),
                        egui::Button::new("Redo  Ctrl+Y")).clicked(){
                        self.editor.redo();ui.close();
                    }
                    ui.separator();
                    if ui.add_enabled(self.selected_id().is_some(),
                        egui::Button::new("Duplicate  Ctrl+D")).clicked(){
                        if let Some(id)=self.selected_id(){
                            self.apply(Action::Duplicate{id});
                        }
                        ui.close();
                    }
                    if ui.add_enabled(self.selected_id().is_some(),
                        egui::Button::new("Remove selected  Del")).clicked(){
                        self.delete_selection();
                        ui.close();
                    }
                });
                ui.menu_button("View",|ui|{
                    if ui.button("Fit material  F").clicked(){
                        self.zoom=1.0;self.pan=egui::Vec2::ZERO;ui.close();
                    }
                    ui.checkbox(&mut self.show_grid,"Show grid");
                    ui.checkbox(&mut self.use_grid,"Snap movement");
                    if ui.button("Material setup").clicked(){
                        self.inspector_tab=InspectorTab::Job;ui.close();
                    }
                });
                ui.menu_button("Drawing",|ui|{
                    if ui.button("Rectangle").clicked(){self.add_shape(ShapeKind::Rectangle);ui.close();}
                    if ui.button("Circle").clicked(){self.add_shape(ShapeKind::Circle);ui.close();}
                    if ui.button("Ellipse").clicked(){self.add_shape(ShapeKind::Ellipse);ui.close();}
                    if ui.button("Star").clicked(){self.add_shape(ShapeKind::Star);ui.close();}
                    ui.separator();
                    if ui.button("Polyline  P").clicked(){
                        self.edit_mode=EditMode::Draw;self.drawing.clear();ui.close();
                    }
                    if ui.button("Circular arc").clicked(){
                        self.add_analytic(Primitive::Arc);ui.close();
                    }
                    if ui.button("Cubic Bézier").clicked(){
                        self.add_analytic(Primitive::Cubic);ui.close();
                    }
                });
                ui.menu_button("Help",|ui|{
                    if ui.button("Controls & shortcuts").clicked(){
                        self.show_help=true;ui.close();
                    }
                    ui.weak("Native Rust design workspace");
                });
                ui.separator();
                let dirty=self.editor.project!=self.saved_project;
                ui.label(if dirty{"● Unsaved changes"}else{"✓ Saved / clean"});
                ui.separator();
                ui.small("CAD only · no CNC export");
            });
        });
        egui::Panel::top("mode-ribbon").show(ui,|ui|{
            ui.horizontal_wrapped(|ui|{
                ui.selectable_value(&mut self.workspace,Workspace::Drawing,"✎  Drawing");
                ui.selectable_value(&mut self.workspace,Workspace::Toolpaths,"⚙  Toolpaths");
                ui.separator();
                if self.workspace==Workspace::Drawing{
                    ui.strong("MODES");
                    ui.selectable_value(&mut self.edit_mode,EditMode::Objects,"↖ Select [V]")
                        .on_hover_text("Select and drag complete vectors");
                    ui.selectable_value(&mut self.edit_mode,EditMode::Nodes,"◇ Nodes [N]")
                        .on_hover_text("Pick and drag anchors and Bézier handles");
                    ui.selectable_value(&mut self.edit_mode,EditMode::Draw,"✎ Pen [P]")
                        .on_hover_text("Click to draw an open polyline or closed polygon");
                    ui.separator();
                    ui.strong("QUICK SHAPES");
                    if ui.button("▭").on_hover_text("Rectangle").clicked(){
                        self.add_shape(ShapeKind::Rectangle);
                    }
                    if ui.button("◯").on_hover_text("Circle").clicked(){
                        self.add_shape(ShapeKind::Circle);
                    }
                    if ui.button("☆").on_hover_text("Star").clicked(){
                        self.add_shape(ShapeKind::Star);
                    }
                    if ui.button("◠").on_hover_text("Circular arc").clicked(){
                        self.add_analytic(Primitive::Arc);
                    }
                }else{
                    ui.colored_label(egui::Color32::YELLOW,
                        "Toolpaths not available · native CAM safety engine not implemented");
                }
                ui.separator();
                if ui.add_enabled(self.editor.can_undo(),egui::Button::new("↶"))
                    .on_hover_text("Undo, Ctrl+Z").clicked(){self.editor.undo();}
                if ui.add_enabled(self.editor.can_redo(),egui::Button::new("↷"))
                    .on_hover_text("Redo, Ctrl+Y").clicked(){self.editor.redo();}
                if ui.button("Fit").on_hover_text("Fit stock to canvas [F]").clicked(){
                    self.zoom=1.0;self.pan=egui::Vec2::ZERO;
                }
            });
        });
        egui::Panel::bottom("status-line").show(ui,|ui|{
            ui.horizontal_wrapped(|ui|{
                let mode=match self.edit_mode{
                    EditMode::Objects=>"Select",EditMode::Nodes=>"Node edit",
                    EditMode::Draw=>"Pen",
                };
                ui.label(egui::RichText::new(format!("  {mode}"))
                    .color(super::theme::ACCENT).strong());
                ui.separator();
                ui.small(format!("{:.0} × {:.0} × {:.1} mm",
                    self.editor.project.stock.width_mm,
                    self.editor.project.stock.height_mm,
                    self.editor.project.stock.thickness_mm));
                ui.separator();
                if let Some(at)=self.cursor_world{
                    ui.small(format!("X {:.2}   Y {:.2} mm",at.x,at.y));
                    ui.separator();
                }
                ui.small(if self.use_grid{"Snap ON"}else{"Snap OFF"});
                ui.separator();
                ui.label(&self.status);
            });
        });
        egui::Panel::left("drawing-palette").resizable(true)
            .default_size(247.0).min_size(212.0).max_size(330.0)
            .show(ui,|ui|{
                egui::ScrollArea::vertical().id_salt("left-palette")
                    .auto_shrink([false,false]).show(ui,|ui|{
                        match self.workspace{
                            Workspace::Drawing=>self.drawing_palette(ui),
                            Workspace::Toolpaths=>self.toolpaths_palette(ui),
                        }
                    });
            });
        egui::Panel::right("object-inspector").resizable(true)
            .default_size(300.0).min_size(244.0).max_size(450.0)
            .show(ui,|ui|{
                egui::ScrollArea::vertical().id_salt("right-properties")
                    .auto_shrink([false,false]).show(ui,|ui|self.inspector(ui));
            });
        egui::CentralPanel::default().show(ui,|ui|{
            match self.workspace{
                Workspace::Drawing=>self.canvas(ui),
                Workspace::Toolpaths=>self.toolpath_placeholder(ui),
            }
        });
        self.overlays(ui.ctx());
    }
    fn toolpath_placeholder(&mut self,ui:&mut egui::Ui){
        ui.add_space(24.0);
        ui.heading("Machining workspace");
        ui.separator();
        ui.label("This workspace is intentionally not active while the Rust CAM engine is under construction.");
        ui.strong("Design is available in the Drawing workspace.");
        ui.label("Before toolpath export, the application must validate stock, cutters, holder envelopes, fixtures, safe motion, posted NC and manual Z re-probing.");
        if ui.button("← Return to Drawing").clicked(){
            self.workspace=Workspace::Drawing;
        }
    }
    fn overlays(&mut self,ctx:&egui::Context) {
        egui::Window::new("Controls & shortcuts")
            .open(&mut self.show_help).resizable(false).show(ctx,|ui|{
                ui.heading("Drawing workspace");
                ui.label("V  Select and move complete objects");
                ui.label("N  Edit nodes and Bézier handles");
                ui.label("P  Draw point-by-point polyline or polygon");
                ui.label("Enter  Complete Pen shape · Esc  Cancel");
                ui.separator();
                ui.label("Mouse wheel  Zoom under pointer");
                ui.label("Middle / right drag  Pan the view");
                ui.label("F  Fit material to drawing window");
                ui.separator();
                ui.label("Ctrl+Z  Undo · Ctrl+Y / Ctrl+Shift+Z  Redo");
                ui.label("Ctrl+D  Duplicate · Delete  Remove selected");
                ui.weak("Shortcuts do not run while text fields have keyboard focus.");
            });
        if let Some(command)=self.pending_document {
            let mut opened=true;
            let mut decision=None;
            egui::Window::new("Unsaved design changes")
                .collapsible(false).resizable(false).open(&mut opened)
                .show(ctx,|ui|{
                    ui.label("The current design has unsaved changes.");
                    ui.label("Discard them to open or create another design?");
                    ui.horizontal(|ui|{
                        if ui.button("Discard changes").clicked(){
                            decision=Some(true);
                        }
                        if ui.button("Keep editing").clicked(){
                            decision=Some(false);
                        }
                    });
                });
            if let Some(confirm)=decision{
                self.pending_document=None;
                if confirm{
                    match command{
                        PendingDocument::New=>self.new_document(),
                        PendingDocument::Open=>self.open_document(),
                    }
                }
            }else if !opened{self.pending_document=None;}
        }
    }
}
