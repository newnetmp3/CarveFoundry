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
            ui.separator();
            ui.label("EXTEND OPEN LINE / ARC / BÉZIER TO REFERENCE");
            let ids=self.selected_ids.iter().copied().collect::<Vec<_>>();
            if !ids.contains(&self.topology_extend_source){
                self.topology_extend_source=ids[0];
            }
            ui.horizontal_wrapped(|ui|{
                ui.label("Source");
                egui::ComboBox::from_id_salt("extend-source-vector")
                    .selected_text(format!("Vector #{}",self.topology_extend_source))
                    .show_ui(ui,|ui|{
                        for id in &ids{
                            ui.selectable_value(&mut self.topology_extend_source,
                                *id,format!("Vector #{id}"));
                        }
                    });
                ui.selectable_value(&mut self.topology_at_start,true,"Start");
                ui.selectable_value(&mut self.topology_at_start,false,"End");
            });
            ui.horizontal_wrapped(|ui|{
                ui.label("Max reach");
                ui.add(egui::DragValue::new(&mut self.topology_extension_limit_mm)
                    .range(0.001..=10000.0).speed(1.0).suffix(" mm"));
            });
            let source=self.topology_extend_source;
            let target=if source==ids[0]{ids[1]}else{ids[0]};
            let source_path=self.editor.project.paths.iter()
                .find(|p|p.id==source).cloned();
            let source_ok=source_path.is_some_and(|p|
                !p.closed && self.editor.project.editable_vector(source));
            let target_ok=self.editor.project.paths.iter().any(|p|p.id==target)
                && self.editor.project.effective_visible(target);
            if ui.add_enabled(source_ok&&target_ok,
                egui::Button::new("Extend end to reference"))
                .on_hover_text("Extend the selected OPEN endpoint along its source geometry: straight continues straight, a true circular arc follows its radius/center, and a Bézier continues the original cubic polynomial with smooth tangent and curvature. Stops at nearest exact crossing with the other selected vector. Source remains editable; Undo restores.")
                .clicked(){
                self.apply(Action::ExtendToBoundary{
                    source_path_id:source,target_path_id:target,
                    at_start:self.topology_at_start,
                    max_distance_mm:self.topology_extension_limit_mm,
                });
            }
            if let Some(p)=source_path{
                if p.closed{
                    ui.small("This source is CLOSED: choose the open Bézier or arc as Source.");
                }else if !self.editor.project.editable_vector(source){
                    ui.small("Source is locked or hidden; unlock and show it to extend.");
                }else{
                    let curve=p.segments[
                        if self.topology_at_start{0}else{p.segments.len()-1}
                    ].curve;
                    let mode=match curve{
                        Curve::Line=>"Straight endpoint: extends on its existing line",
                        Curve::Arc{..}=>"Circular endpoint: continues exact circle and winding",
                        Curve::Cubic{..}=>"Bézier endpoint: continues exact polynomial with G² geometric smoothness",
                    };
                    ui.small(mode);
                }
            }else{
                ui.small("Choose a source analytic vector to extend.");
            }
            if !target_ok{
                ui.small("Reference is missing or hidden; choose two visible analytic vectors.");
            }
            ui.small("The other selected vector is the reference. A failed or out-of-reach crossing reports why; Undo restores geometry.");
        }
        ui.separator();
        ui.strong("INTERSECTIONS · LINES / ARCS / BÉZIERS");
        if self.topology_scan_source!=only{
            self.topology_crossings.clear();
            self.topology_selected_crossing=0;
            self.topology_scan_source=None;
            self.topology_pick_crossing=false;
        }
        if let Some(source_id)=only{
            ui.horizontal_wrapped(|ui|{
                if ui.button("Find intersections").on_hover_text(
                    "Scan current source vector against other visible analytic paths. Source-geometry crossings for lines, true arcs and cubic Bézier curves. Coincident/unsolved overlaps are reported rather than approximated.").clicked(){
                    self.topology_pick_crossing=false;
                    match carvefoundry_core::find_intersections(
                        &self.editor.project,source_id){
                        Ok(scan)=>{
                            self.topology_crossings=scan.hits;
                            self.topology_skipped_pairs=scan.unsupported_pairs;
                            self.topology_scan_source=Some(source_id);
                            self.topology_selected_crossing=0;
                            self.status=format!("Found {} exact crossings; {} unsupported edge pairs",
                                self.topology_crossings.len(),
                                self.topology_skipped_pairs);
                        }
                        Err(error)=>{
                            self.topology_crossings.clear();
                            self.topology_scan_source=None;
                            self.status=format!("Intersection scan rejected: {error}");
                        }
                    }
                }
                if !self.topology_crossings.is_empty(){
                    ui.checkbox(&mut self.topology_pick_crossing,"Pick marker on canvas")
                        .on_hover_text("Click a numbered crossing marker; this temporarily suspends normal object selection.");
                }
            });
            if self.topology_scan_source==Some(source_id) {
                if self.topology_crossings.is_empty(){
                    ui.small(format!("No supported interior crossings ({} overlapping/indeterminate edge pairs).",
                        self.topology_skipped_pairs));
                }else{
                    let i=self.topology_selected_crossing.min(self.topology_crossings.len()-1);
                    self.topology_selected_crossing=i;
                    egui::ComboBox::from_id_salt(("crossing",source_id))
                        .selected_text(format!("Crossing {} of {}",i+1,self.topology_crossings.len()))
                        .width(ui.available_width().min(245.0))
                        .show_ui(ui,|ui|{
                            for (j,hit) in self.topology_crossings.iter().enumerate(){
                                ui.selectable_value(&mut self.topology_selected_crossing,j,
                                    format!("#{} · X {:.3}  Y {:.3} mm · vector {}",
                                        j+1,hit.position.x,hit.position.y,hit.target_path_id));
                            }
                        });
                    let hit=self.topology_crossings[i].clone();
                    ui.small(format!("Edge {} at t={:.5} · reference vector {}",
                        hit.source_segment_id,hit.source_t,hit.target_path_id));
                    ui.small(format!("{} overlapping/indeterminate edge pairs (not guessed).",
                        self.topology_skipped_pairs));
                    ui.horizontal_wrapped(|ui|{
                        if ui.button("Split at crossing")
                            .on_hover_text("Revalidate exact crossing against current paths. Split the source edge analytically; one Undo step.").clicked(){
                            self.apply(Action::SplitAtIntersection{hit:hit.clone()});
                            self.topology_crossings.clear();
                            self.topology_pick_crossing=false;
                            self.topology_scan_source=None;
                        }
                        if ui.button("Trim end to crossing")
                            .on_hover_text("Trim the selected open path's Start or End terminal segment exactly to this crossing; intermediate segment crossings are refused.").clicked(){
                            self.apply(Action::TrimAtIntersection{
                                hit,at_start:self.topology_at_start,
                            });
                            self.topology_crossings.clear();
                            self.topology_pick_crossing=false;
                            self.topology_scan_source=None;
                        }
                    });
                }
            }
        }else{
            ui.small("Select one source vector, then scan against other visible vectors.");
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
        ui.small("Offset: straight contours or exact circular arcs / concentric circle chains.");
        if ui.add_enabled(eligible,egui::Button::new("Create offset vector"))
            .on_hover_text("New editable offset; open: + left / - right, closed: + outward / - inward. Exact straight paths or single circular arcs and concentric circular rings; general Béziers rejected.").clicked(){
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
                .on_hover_text("Select a line-line node in Nodes mode (open interior or any closed corner); creates a true radius/center tangent arc.").clicked()
                && let Some(node_id)=node{
                self.apply(Action::Corner{path_id,node_id,
                    size_mm:self.topology_distance_mm,fillet:true});
            }
            if ui.add_enabled(eligible&&node.is_some(),
                egui::Button::new("Chamfer selected node"))
                .on_hover_text("Select a line-line node (open interior or closed vertex) in Nodes mode. Bevel both edges by this distance.").clicked()
                && let Some(node_id)=node{
                self.apply(Action::Corner{path_id,node_id,
                    size_mm:self.topology_distance_mm,fillet:false});
            }
        });
        ui.small("Corners: line-line only, including closed loops. Cubic/mixed curve offset and intersections remain unsupported.");
    }
}
fn curve_name(c:Curve)->&'static str{
    match c{Curve::Line=>"Line",Curve::Arc{..}=>"Circular arc",
        Curve::Cubic{..}=>"Cubic Bézier"}
}
