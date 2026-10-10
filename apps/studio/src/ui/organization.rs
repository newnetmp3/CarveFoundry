//! Native layer/group explorer. All changes go through the validated Editor.
use super::super::{EditMode,InspectorTab,Studio};
use super::icons::{self,Icon};
use carvefoundry_core::Action;
use eframe::egui;
impl Studio {
    pub(crate) fn groups_panel(&mut self,ui:&mut egui::Ui){
        ui.horizontal(|ui|{
            ui.strong("GROUPS");
            ui.weak(format!("{} groups",self.editor.project.groups.len()));
        });
        if self.selected_ids.len()>=2{
            ui.horizontal(|ui|{
                ui.add(egui::TextEdit::singleline(&mut self.group_name_draft)
                    .hint_text("Group name").desired_width(145.0));
                if ui.button("Group selected").on_hover_text(
                    "Create one selectable/movable group from the current editable vector selection")
                    .clicked(){
                    let ids=self.selected_ids.iter().copied().collect();
                    let before=self.editor.project.next_id;
                    self.apply(Action::MakeGroup{
                        ids,name:self.group_name_draft.clone(),
                    });
                    if self.editor.project.groups.iter().any(|g|g.id==before){
                        self.active_group_id=Some(before);
                    }
                }
            });
        } else {
            ui.small("Select two or more vectors and use Group selected.");
        }
        let groups=self.editor.project.groups.clone();
        for group in groups{
            let chosen=self.active_group_id==Some(group.id);
            ui.horizontal(|ui|{
                if icons::small(ui,if group.visible{"Hide group"}else{"Show group"},
                    if group.visible{Icon::Eye}else{Icon::Hidden}).clicked(){
                    self.apply(Action::SetGroupVisible{id:group.id,visible:!group.visible});
                    self.reconcile_selection();
                }
                if icons::small(ui,if group.locked{"Unlock group"}else{"Lock group"},
                    if group.locked{Icon::Lock}else{Icon::Unlock}).clicked(){
                    self.apply(Action::SetGroupLocked{id:group.id,locked:!group.locked});
                }
                if ui.selectable_label(chosen,format!("{} ({})",group.name,
                    group.members.len())).clicked(){
                    self.active_group_id=Some(group.id);
                    self.group_name_draft=group.name.clone();
                    self.select_entire_group(group.id);
                }
            });
        }
        if let Some(id)=self.active_group_id {
            if let Some(group)=self.editor.project.groups.iter().find(|g|g.id==id).cloned(){
                ui.horizontal_wrapped(|ui|{
                    if ui.button("Rename group").clicked(){
                        self.apply(Action::RenameGroup{
                            id,name:self.group_name_draft.clone(),
                        });
                    }
                    if ui.button("Ungroup").on_hover_text(
                        "Remove grouping while retaining every original vector").clicked(){
                        self.apply(Action::Ungroup{id});
                        self.active_group_id=None;
                        self.reconcile_selection();
                    }
                });
                ui.small(format!("{} linked vectors · each retains editable nodes",
                    group.members.len()));
            }else{
                self.active_group_id=None;
            }
        }
        ui.separator();
    }
    pub(crate) fn layers_panel(&mut self,ui:&mut egui::Ui){
        ui.heading("DESIGN LAYERS");
        ui.small("Virtual Base layer is always visible and editable. Each vector may belong to one custom layer.");
        ui.horizontal(|ui|{
            ui.add(egui::TextEdit::singleline(&mut self.layer_name_draft)
                .hint_text("New layer name").desired_width(180.0));
            if ui.button("Add layer").clicked(){
                let id=self.editor.project.next_id;
                self.apply(Action::AddLayer{name:self.layer_name_draft.clone()});
                if self.editor.project.layers.iter().any(|l|l.id==id){
                    self.active_layer_id=Some(id);
                }
            }
        });
        ui.separator();
        let total=self.editor.project.paths.len()+self.editor.project.contours.len();
        let base_count=total-self.editor.project.layer_members.len();
        ui.label(format!("Base layer · {base_count} vectors"));
        if !self.selected_ids.is_empty()
            && ui.button("Move selection to Base").clicked(){
            self.apply(Action::AssignLayer{
                ids:self.selected_ids.iter().copied().collect(),layer_id:0,
            });
        }
        let layers=self.editor.project.layers.clone();
        for layer in layers {
            let count=self.editor.project.layer_members.iter()
                .filter(|m|m.layer_id==layer.id).count();
            ui.horizontal(|ui|{
                if icons::small(ui,if layer.visible{"Hide layer"}else{"Show layer"},
                    if layer.visible{Icon::Eye}else{Icon::Hidden}).clicked(){
                    self.apply(Action::SetLayerVisible{id:layer.id,visible:!layer.visible});
                    self.reconcile_selection();
                }
                if icons::small(ui,if layer.locked{"Unlock layer"}else{"Lock layer"},
                    if layer.locked{Icon::Lock}else{Icon::Unlock}).clicked(){
                    self.apply(Action::SetLayerLocked{id:layer.id,locked:!layer.locked});
                }
                if ui.selectable_label(self.active_layer_id==Some(layer.id),
                    format!("{} ({count})",layer.name)).clicked(){
                    self.active_layer_id=Some(layer.id);
                    self.layer_name_draft=layer.name.clone();
                }
            });
        }
        if let Some(id)=self.active_layer_id{
            if let Some(layer)=self.editor.project.layers.iter().find(|l|l.id==id).cloned(){
                ui.separator();
                ui.strong(format!("Selected layer: {}",layer.name));
                ui.label("Rename");
                ui.add(egui::TextEdit::singleline(&mut self.layer_name_draft)
                    .desired_width(ui.available_width()));
                ui.horizontal_wrapped(|ui|{
                    if ui.button("Rename").clicked(){
                        self.apply(Action::RenameLayer{id,name:self.layer_name_draft.clone()});
                    }
                    if ui.button("Delete layer").on_hover_text(
                        "Move its vectors to Base, then delete only the layer").clicked(){
                        self.apply(Action::RemoveLayer{id});
                        self.active_layer_id=None;
                    }
                });
                if !self.selected_ids.is_empty(){
                    if ui.add_enabled(layer.visible&&!layer.locked,
                        egui::Button::new(format!(
                            "Move {} selected to layer",self.selected_ids.len())))
                        .clicked(){
                        self.apply(Action::AssignLayer{
                            ids:self.selected_ids.iter().copied().collect(),layer_id:id,
                        });
                    }
                }else{
                    ui.weak("Select vectors in Objects to assign them here.");
                }
            }else{self.active_layer_id=None;}
        }
        ui.separator();
        if ui.button("Back to Objects").clicked(){
            self.inspector_tab=InspectorTab::Objects;
            self.edit_mode=EditMode::Objects;
        }
    }
}
