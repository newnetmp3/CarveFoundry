//! Right-side object tree and focused property inspector.
//! Model data stays owned by carvefoundry-core; this module only dispatches Actions.
use super::super::{InspectorTab,Studio,EditMode};
use carvefoundry_core::{Action,Curve,Fixture,Point};
use eframe::egui;

impl Studio {
    pub(crate) fn inspector(&mut self,ui:&mut egui::Ui) {
        ui.horizontal(|ui|{
            ui.heading("DESIGN");
            ui.weak("Explorer");
        });
        ui.horizontal_wrapped(|ui|{
            ui.selectable_value(&mut self.inspector_tab,InspectorTab::Objects,"Objects");
            ui.selectable_value(&mut self.inspector_tab,InspectorTab::Properties,"Properties");
            ui.selectable_value(&mut self.inspector_tab,InspectorTab::Job,"Material");
        });
        ui.separator();
        match self.inspector_tab{
            InspectorTab::Objects=>self.objects_tab(ui),
            InspectorTab::Properties=>self.object_properties(ui),
            InspectorTab::Job=>self.job_tab(ui),
        }
    }
    fn objects_tab(&mut self,ui:&mut egui::Ui) {
        let n=self.editor.project.paths.len()+self.editor.project.contours.len();
        ui.label(format!("{n} vectors  ·  {} fixtures",self.editor.project.fixtures.len()));
        ui.small("Click to select · Shift/Ctrl-click to add or remove. Drag blank canvas for a selection box.");
        ui.label(format!("{} selected",self.selected_ids.len()));
        ui.separator();
        let entries:Vec<_>=self.editor.project.paths.iter().map(|p|
            (p.id,p.name.clone(),p.visible,p.locked,true))
            .chain(self.editor.project.contours.iter().map(|p|
                (p.id,p.name.clone(),p.visible,p.locked,false)))
            .collect();
        egui::ScrollArea::vertical().id_salt("object-tree")
            .max_height(280.0)
            .show(ui,|ui|{
                for (id,name,visible,locked,is_path) in entries {
                    let selected=self.selected_ids.contains(&id);
                    ui.horizontal(|ui|{
                        if ui.small_button(if visible{"◉"}else{"○"})
                            .on_hover_text(if visible{"Hide vector"}else{"Show vector"})
                            .clicked(){self.apply(Action::SetVisible{id,visible:!visible});}
                        if ui.small_button(if locked{"🔒"}else{"◌"})
                            .on_hover_text(if locked{"Unlock vector"}else{"Lock vector"})
                            .clicked(){
                                if is_path{self.apply(Action::SetPathLocked{id,locked:!locked});}
                                else{self.apply(Action::SetLocked{id,locked:!locked});}
                            }
                        let marker=if is_path{"⌁"}else{"▱"};
                        if ui.selectable_label(selected,format!("{marker}  {name}"))
                            .on_hover_text("Select and inspect this vector").clicked(){
                            let additive=ui.input(|i|i.modifiers.shift||i.modifiers.command);
                            self.select_vector(Some(id),additive);
                        }
                    });
                }
            });
        ui.separator();
        if self.selected_ids.len()>1{
            let ids:Vec<u64>=self.selected_ids.iter().copied().collect();
            ui.strong(format!("{} selected vectors",ids.len()));
            ui.small("Drag any selected vector to move the entire selection.");
            ui.horizontal_wrapped(|ui|{
                if ui.button("Duplicate selection").clicked(){
                    let first=self.editor.project.next_id;
                    self.apply(Action::DuplicateMany{ids:ids.clone()});
                    if self.editor.project.next_id==first+ids.len() as u64{
                        self.selected_ids=(first..first+ids.len() as u64).collect();
                        self.selected_path=None;self.selected=None;
                        self.reconcile_selection();
                    }
                }
                if ui.button("Delete selection").clicked(){
                    self.apply(Action::RemoveMany{ids});
                    self.reconcile_selection();
                }
                if ui.button("Clear").clicked(){
                    self.select_vector(None,false);
                }
            });
            return;
        }
        if let Some(id)=self.selected_id(){
            ui.strong("Selected vector");
            if let Some(p)=self.editor.project.paths.iter().find(|p|p.id==id){
                ui.label(&p.name);
                ui.small(format!("{} nodes · {} segments",p.nodes.len(),p.segments.len()));
            }else if let Some(p)=self.editor.project.contours.iter().find(|p|p.id==id){
                ui.label(&p.name);
                ui.small(format!("{} contour vertices",p.vertices.len()));
            }
            if ui.button("Edit selected properties →").clicked(){
                self.inspector_tab=InspectorTab::Properties;
            }
            ui.horizontal_wrapped(|ui|{
                if ui.button("Duplicate").on_hover_text("Copy selected geometry").clicked(){
                    let new_id=self.editor.project.next_id;
                    self.apply(Action::Duplicate{id});
                    if self.editor.project.paths.iter().any(|p|p.id==new_id){
                        self.selected_path=Some(new_id);self.selected=None;
                    }else if self.editor.project.contours.iter().any(|p|p.id==new_id){
                        self.selected=Some(new_id);self.selected_path=None;
                    }
                }
                if ui.button("Hide").clicked(){
                    self.apply(Action::SetVisible{id,visible:false});
                    self.reconcile_selection();
                }
            });
        }else{
            ui.weak("Nothing selected");
            ui.small("Press V and click a shape in the drawing area, or select it from the list above.");
        }
    }
    fn object_properties(&mut self,ui:&mut egui::Ui) {
        if self.selected_ids.len()>1{
            ui.heading(format!("{} selected vectors",self.selected_ids.len()));
            ui.label("Move them together in Select mode, or use the Objects tab for Duplicate/Delete selection.");
            if ui.button("Open Objects tab").clicked(){
                self.inspector_tab=InspectorTab::Objects;
            }
            return;
        }
        let path=self.editor.project.paths.iter()
            .find(|p|Some(p.id)==self.selected_path).cloned();
        if let Some(path)=path {
            ui.strong(&path.name);
            if self.rename_target!=Some(path.id){
                self.rename_target=Some(path.id);
                self.rename_draft=path.name.clone();
            }
            ui.horizontal(|ui|{
                ui.add(egui::TextEdit::singleline(&mut self.rename_draft)
                    .hint_text("Vector name").desired_width(178.0));
                if ui.add_enabled(!path.locked,
                    egui::Button::new("Rename")).clicked(){
                    let desired=self.rename_draft.trim().to_owned();
                    self.apply(Action::RenamePath{id:path.id,name:desired});
                }
            });
            ui.small(format!("Path #{} · {} nodes · {} segments",
                path.id,path.nodes.len(),path.segments.len()));
            ui.separator();
            ui.strong("Object position");
            let mut origin=path.origin;
            let mut changed=false;
            ui.horizontal(|ui|{
                ui.label("X");
                changed|=ui.add(egui::DragValue::new(&mut origin.x)
                    .speed(0.25).suffix(" mm")).changed();
                ui.label("Y");
                changed|=ui.add(egui::DragValue::new(&mut origin.y)
                    .speed(0.25).suffix(" mm")).changed();
            });
            if changed{self.apply(Action::MovePath{id:path.id,origin});}
            let mut locked=path.locked;
            if ui.checkbox(&mut locked,"Lock editing").changed(){
                self.apply(Action::SetPathLocked{id:path.id,locked});
            }
            ui.horizontal(|ui|{
                if ui.add_enabled(!locked,egui::Button::new(
                    if path.closed{"Open path"}else{"Close outline"}
                )).clicked(){
                    self.apply(Action::SetPathClosed{id:path.id,closed:!path.closed});
                }
                if ui.add_enabled(!locked,egui::Button::new("Delete")).clicked(){
                    self.apply(Action::RemovePath{id:path.id});
                    self.selected_path=None;self.selected_node=None;
                }
            });
            ui.separator();
            ui.horizontal(|ui|{
                ui.strong("Edit nodes");
                if ui.button("Node mode [N]").clicked(){
                    self.edit_mode=EditMode::Nodes;
                }
            });
            egui::ScrollArea::vertical().id_salt("node-list")
                .max_height(145.0).show(ui,|ui|{
                    for node in &path.nodes {
                        ui.selectable_value(&mut self.selected_node,Some(node.id),
                            format!("#{}   X {:.2}   Y {:.2}",
                                node.id,node.position.x,node.position.y));
                    }
                });
            if let Some(node)=path.nodes.iter().find(|n|Some(n.id)==self.selected_node){
                ui.strong(format!("Anchor #{}",node.id));
                let mut pos=node.position;
                let mut changed=false;
                ui.horizontal(|ui|{
                    ui.label("X");
                    changed|=ui.add(egui::DragValue::new(&mut pos.x)
                        .speed(0.1).suffix(" mm")).changed();
                    ui.label("Y");
                    changed|=ui.add(egui::DragValue::new(&mut pos.y)
                        .speed(0.1).suffix(" mm")).changed();
                });
                if changed{self.apply(Action::MoveNode{
                    path_id:path.id,node_id:node.id,position:pos,
                });}
                ui.horizontal_wrapped(|ui|{
                    if ui.add_enabled(!locked,egui::Button::new("Insert midpoint"))
                        .on_hover_text("Split next straight segment into two line edges")
                        .clicked(){
                        let new_id=path.next_element_id;
                        self.apply(Action::InsertNodeAfter{
                            path_id:path.id,node_id:node.id,
                        });
                        if self.editor.project.paths.iter().any(|p|
                            p.id==path.id && p.nodes.iter().any(|n|n.id==new_id)){
                            self.selected_node=Some(new_id);
                        }
                    }
                    if ui.add_enabled(!locked,egui::Button::new("Remove node"))
                        .on_hover_text("Only lossless line junction deletions are supported")
                        .clicked(){
                        self.apply(Action::RemoveNode{
                            path_id:path.id,node_id:node.id,
                        });
                        self.selected_node=None;
                    }
                });
            }
            if path.segments.iter().any(|s|matches!(s.curve,Curve::Cubic{..})){
                ui.separator();
                ui.strong("Bézier control handles");
                for segment in &path.segments{
                    if let Curve::Cubic{control1,control2}=segment.curve{
                        ui.horizontal(|ui|{
                            if ui.selectable_label(self.selected_handle==Some((segment.id,1)),
                                format!("S{} H1",segment.id)).clicked(){
                                self.selected_handle=Some((segment.id,1));
                            }
                            if ui.selectable_label(self.selected_handle==Some((segment.id,2)),
                                "H2").clicked(){
                                self.selected_handle=Some((segment.id,2));
                            }
                        });
                        if let Some((id,handle))=self.selected_handle
                            && id==segment.id {
                            let mut pos=if handle==1{control1}else{control2};
                            let mut changed=false;
                            ui.horizontal(|ui|{
                                ui.label("X");
                                changed|=ui.add(egui::DragValue::new(&mut pos.x)
                                    .speed(0.1).suffix(" mm")).changed();
                                ui.label("Y");
                                changed|=ui.add(egui::DragValue::new(&mut pos.y)
                                    .speed(0.1).suffix(" mm")).changed();
                            });
                            if changed{self.apply(Action::MoveControl{
                                path_id:path.id,segment_id:id,handle,position:pos,
                            });}
                        }
                    }
                }
            }
        }else if let Some(contour)=self.editor.project.contours.iter()
            .find(|p|Some(p.id)==self.selected).cloned(){
            ui.strong(format!("Legacy vector · {}",contour.name));
            ui.small("Originally created using the early Rust contour tools");
            let mut x=contour.origin.x;let mut y=contour.origin.y;
            let mut changed=false;
            ui.horizontal(|ui|{
                ui.label("X");
                changed|=ui.add(egui::DragValue::new(&mut x).suffix(" mm")).changed();
                ui.label("Y");
                changed|=ui.add(egui::DragValue::new(&mut y).suffix(" mm")).changed();
            });
            if changed{self.apply(Action::Move{id:contour.id,origin:Point::new(x,y)});}
            if ui.add_enabled(!contour.locked,
                egui::Button::new("Convert to editable nodes")).clicked(){
                self.apply(Action::ConvertContour{id:contour.id});
                if self.editor.project.paths.iter().any(|p|p.id==contour.id){
                    self.selected_path=Some(contour.id);self.selected=None;
                    self.edit_mode=EditMode::Nodes;
                }
            }
        }else{
            ui.heading("Nothing selected");
            ui.label("Select a vector in the drawing or from Objects.");
            if ui.button("Create a rectangle").clicked(){
                self.add_shape(carvefoundry_core::ShapeKind::Rectangle);
            }
        }
    }
    fn job_tab(&mut self,ui:&mut egui::Ui) {
        ui.strong("Project name");
        ui.add(egui::TextEdit::singleline(&mut self.project_name_draft)
            .desired_width(ui.available_width().min(260.0)));
        if ui.button("Rename project").clicked(){
            let desired=self.project_name_draft.trim().to_owned();
            self.apply(Action::RenameProject{name:desired});
        }
        ui.separator();
        ui.strong("Material setup");
        ui.label("Work XY0: stock bottom-left");
        ui.label("Work Z0: material top");
        let mut stock=self.editor.project.stock.clone();
        let mut changed=false;
        ui.horizontal(|ui|{
            ui.label("Width");
            changed|=ui.add(egui::DragValue::new(&mut stock.width_mm)
                .range(1.0..=100_000.0).suffix(" mm")).changed();
        });
        ui.horizontal(|ui|{
            ui.label("Height");
            changed|=ui.add(egui::DragValue::new(&mut stock.height_mm)
                .range(1.0..=100_000.0).suffix(" mm")).changed();
        });
        ui.horizontal(|ui|{
            ui.label("Thickness");
            changed|=ui.add(egui::DragValue::new(&mut stock.thickness_mm)
                .range(0.1..=100_000.0).suffix(" mm")).changed();
        });
        if changed{self.apply(Action::ChangeStock(stock));}
        ui.separator();
        ui.strong("Fixture inventory");
        ui.colored_label(egui::Color32::YELLOW,
            "Visual keep-outs only; no cutter/holder verification exists.");
        for fixture in &self.editor.project.fixtures {
            ui.group(|ui|{
                ui.strong(&fixture.name);
                ui.small(format!("X {:.1}..{:.1}  Y {:.1}..{:.1}",
                    fixture.min.x,fixture.max.x,fixture.min.y,fixture.max.y));
                ui.small(format!("Top Z {:+.1} mm  margin {:.1} mm",
                    fixture.top_z_mm,fixture.clearance_mm));
            });
        }
        if ui.button("Add example left fence").on_hover_text(
            "Example is 23 mm above machine bed. Verify dimensions before any future machining."
        ).clicked(){
            self.apply(Action::AddFixture(Fixture{
                name:format!("Left fence {}",self.editor.project.fixtures.len()+1),
                min:Point::new(-10.0,0.0),
                max:Point::new(0.0,self.editor.project.stock.height_mm),
                top_z_mm:23.0-self.editor.project.stock.thickness_mm,
                clearance_mm:2.0,
            }));
        }
        ui.separator();
        for warning in self.editor.project.design_warnings(){
            ui.colored_label(egui::Color32::YELLOW,warning);
        }
        ui.weak("No toolpaths, preflight or machine export available.");
    }
}
