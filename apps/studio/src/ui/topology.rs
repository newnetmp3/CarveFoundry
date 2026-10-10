//! Source-accurate 2D topology controls, never CAM vectors or preview sampling.
use super::super::Studio;
use carvefoundry_core::{Action,Curve};
use eframe::egui;

impl Studio {
    pub(crate) fn topology_tools(&mut self,ui:&mut egui::Ui){
        let only=if self.selected_ids.len()==1 {
            self.selected_ids.iter().next().copied()
        }else{None};
        let selected=only.and_then(|id|self.editor.project.paths.iter()
            .find(|p|p.id==id)).cloned();
        let eligible=only.is_some_and(|id|self.editor.project.editable_vector(id));
        let group_two=self.selected_ids.len()==2;
        ui.weak("Exact source curves — operations are one-step Undo. No CAM/G-code.");
        if group_two {
            ui.label("JOIN TWO OPEN PATHS");
            ui.horizontal_wrapped(|ui|{
                ui.label("Gap ≤");
                ui.add(egui::DragValue::new(&mut self.topology_join_mm)
                    .range(0.0..=5.0).speed(0.01).suffix(" mm"));
                if ui.button("Join selected").on_hover_text(
                    "Join closest open endpoints. A real line bridges a small gap; circles/cubics remain exact. Both paths must share layer and group.")
                    .clicked(){
                    let ids=self.selected_ids.iter().copied().collect::<Vec<_>>();
                    let a=ids[0];let b=ids[1];
                    self.apply(Action::JoinOpen{
                        first_id:a,second_id:b,
                        tolerance_mm:self.topology_join_mm,
                    });
                    if self.editor.project.paths.iter().any(|p|p.id==a)
                        && self.editor.project.paths.iter().all(|p|p.id!=b){
                        self.select_vector(Some(a),false);
                    }
                }
            });
        }
        let Some(path)=selected else{
            ui.small("Select one editable analytic vector, or two open paths to Join.");
            return;
        };
        let path_id=path.id;
        ui.horizontal_wrapped(|ui|{
            ui.label(format!("Vector #{} · {} edges",path_id,path.segments.len()));
            ui.label(if path.closed{"Closed"}else{"Open"});
        });
        ui.horizontal_wrapped(|ui|{
            ui.label("Fraction");
            ui.add(egui::DragValue::new(&mut self.topology_fraction)
                .range(0.0001..=0.9999).speed(0.01)
                .max_decimals(4));
            ui.label("Corner / offset");
            ui.add(egui::DragValue::new(&mut self.topology_distance_mm)
                .range(0.001..=10000.0).speed(0.25).suffix(" mm"));
        });
        ui.horizontal_wrapped(|ui|{
            ui.selectable_value(&mut self.topology_at_start,true,"Start");
            ui.selectable_value(&mut self.topology_at_start,false,"End");
            ui.weak("Choose open-path end to trim/extend");
        });
        ui.separator();
        ui.label("SPLIT EXACT CURVE AT FRACTION");
        let chosen_exists=path.segments.iter().any(|s|s.id==self.topology_segment);
        let segment=if chosen_exists{
            self.topology_segment
        }else{
            path.segments[0].id
        };
        self.topology_segment=segment;
        egui::ComboBox::from_id_salt(("topology-edge",path_id))
            .selected_text(path.segments.iter().enumerate()
                .find(|(_,s)|s.id==segment)
                .map_or_else(||"Choose edge".to_string(),|(i,s)|
                    format!("Edge {} · {}",i+1,curve_name(s.curve))))
            .width(ui.available_width().min(245.0))
            .show_ui(ui,|ui|{
                for (i,s) in path.segments.iter().enumerate(){
                    ui.selectable_value(&mut self.topology_segment,s.id,
                        format!("Edge {} · {}",i+1,curve_name(s.curve)));
                }
            });
        if ui.add_enabled(eligible,egui::Button::new("Split selected edge"))
            .on_hover_text("Insert an exact node on a line, true arc or cubic, keeping the original geometry and segment identity").clicked(){
            self.apply(Action::SplitSegment{
                path_id,segment_id:self.topology_segment,
                t:self.topology_fraction,
            });
        }
        ui.separator();
        ui.label("ENDPOINT TOOLS");
        ui.horizontal_wrapped(|ui|{
            if ui.add_enabled(eligible&&!path.closed,egui::Button::new("Trim end"))
                .on_hover_text("Shorten the first or last segment analytically. No curve tessellation.").clicked(){
                self.apply(Action::TrimEndpoint{path_id,
                    at_start:self.topology_at_start,t:self.topology_fraction});
            }
            if ui.add_enabled(eligible&&!path.closed,
                egui::Button::new("Extend straight end"))
                .on_hover_text("Extend only a straight terminal edge, in its original direction").clicked(){
                self.apply(Action::ExtendLine{path_id,
                    at_start:self.topology_at_start,
                    distance_mm:self.topology_distance_mm.abs()});
            }
        });
        ui.separator();
        ui.label("PARALLEL OFFSETS AND CORNERS");
        if ui.add_enabled(eligible,egui::Button::new("Create offset vector"))
            .on_hover_text("New editable parallel outline; open paths: + left / - right, closed: + outward / - inward. Straight edges only; rejects ambiguous/self-intersecting offsets.").clicked(){
            let newid=self.editor.project.next_id;
            self.apply(Action::OffsetLines{path_id,
                distance_mm:self.topology_distance_mm});
            if self.editor.project.paths.iter().any(|p|p.id==newid){
                self.select_vector(Some(newid),false);
            }
        }
        let node=self.selected_node;
        ui.horizontal_wrapped(|ui|{
            if ui.add_enabled(eligible&&node.is_some(),
                egui::Button::new("Fillet selected node"))
                .on_hover_text("Select an INTERIOR line-line node in Nodes mode. Builds a true tangent circular arc with this radius.").clicked()
                && let Some(node_id)=node{
                self.apply(Action::Corner{path_id,node_id,
                    size_mm:self.topology_distance_mm,fillet:true});
            }
            if ui.add_enabled(eligible&&node.is_some(),
                egui::Button::new("Chamfer selected node"))
                .on_hover_text("Select an interior line-line node in Nodes mode. Bevel both adjacent edges by this distance.").clicked()
                && let Some(node_id)=node{
                self.apply(Action::Corner{path_id,node_id,
                    size_mm:self.topology_distance_mm,fillet:false});
            }
        });
        ui.small("Fillet/chamfer: open line-line interior node only. Curve offsets and closed-corner fillets remain unavailable until exact algorithms land.");
    }
}
fn curve_name(c:Curve)->&'static str{
    match c{Curve::Line=>"Line",Curve::Arc{..}=>"Circular arc",
        Curve::Cubic{..}=>"Cubic Bézier"}
}
