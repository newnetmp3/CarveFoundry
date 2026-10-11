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
            let source_ok=source_path.as_ref().is_some_and(|p|
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
        // Read-only source-accurate compound contour analysis. Cache only
        // a display interpretation; compare all original vector geometry
        // every frame so drag, document load or selection changes cannot
        // leave stale hole classifications on screen.
        let picked=self.selected_ids.iter().filter_map(|id|
            self.editor.project.paths.iter().find(|p|p.id==*id).cloned()
        ).collect::<Vec<_>>();
        if self.topology_compound_checked!=picked {
            self.topology_compound_checked.clear();
            self.topology_compound_roles.clear();
        }
        if self.selected_ids.len()>=2 {
            ui.separator();
            ui.strong("COMPOUND CONTOURS · HOLES / ISLANDS");
            ui.small("Select 2–32 closed line/true-circle vectors. Check boundaries analytically and classify outer regions, holes and nested islands without changing CAD geometry. Cubic curves or touching/crossing loops are refused.");
            if ui.button("Analyze selected closed contours")
                .on_hover_text("Read-only analytic containment. Rejects open vectors, cubics, self-crossings, coincident overlaps, boundary contact and excessive edge-pair counts. The resulting roles are CAD design information only, NOT pocket machining or cutter clearance.").clicked(){
                self.topology_compound_roles.clear();
                self.topology_compound_checked.clear();
                if picked.len()!=self.selected_ids.len() {
                    self.status="Compound analysis requires only editable analytic closed vectors, not polygon contour objects".into();
                }else{
                    match carvefoundry_core::analyze_compound_paths(&picked){
                        Ok(roles)=>{
                            let holes=roles.iter().filter(|r|
                                r.role==carvefoundry_core::CompoundRole::Hole
                            ).count();
                            self.status=format!(
                                "Compound CAD: {} loops, {} holes; read-only, no machining output",
                                roles.len(),holes);
                            self.topology_compound_checked=picked.clone();
                            self.topology_compound_roles=roles;
                        }
                        Err(problem)=>{
                            self.status=format!("Compound analysis refused: {problem}");
                        }
                    }
                }
            }
            ui.horizontal_wrapped(|ui|{
                ui.label("Region name");
                ui.text_edit_singleline(&mut self.topology_region_name_draft);
            });
            if ui.button("Save as editable compound region")
                .on_hover_text("Save selected independent closed source vectors as a persistent even/odd CAD region. Requires proven disjoint boundaries; no flattened curves, no toolpaths. Undo restores the design.").clicked(){
                self.apply(Action::SaveCompoundRegion{
                    ids:picked.iter().map(|p|p.id).collect(),
                    name:self.topology_region_name_draft.clone(),
                });
            }
            if !self.topology_compound_roles.is_empty(){
                ui.weak("Verified nested boundary roles (not toolpaths):");
                for role in &self.topology_compound_roles{
                    let kind=match role.role{
                        carvefoundry_core::CompoundRole::Outline=>"Outline / island",
                        carvefoundry_core::CompoundRole::Hole=>"Hole / empty region",
                    };
                    let parent=role.parent_path_id
                        .map_or_else(||"none".to_string(),|id|format!("#{id}"));
                    ui.small(format!(
                        "Vector #{} · {} · depth {} · parent {}",
                        role.path_id,kind,role.depth,parent
                    ));
                }
            }
        }
        // Durable CAD region display uses saved source IDs, even if
        // only one member is currently selected. No stale cache.
        let selected_region=self.editor.project.compound_regions.iter()
            .find(|r|r.path_ids.iter().any(|id|self.selected_ids.contains(id)))
            .cloned();
        if let Some(region)=selected_region{
            ui.separator();
            ui.strong(format!("SAVED COMPOUND · {}",region.name));
            ui.small(format!("CAD region #{} · {} independent source loops",
                region.id,region.path_ids.len()));
            let sources=region.path_ids.iter().filter_map(|id|
                self.editor.project.paths.iter().find(|p|p.id==*id).cloned()
            ).collect::<Vec<_>>();
            if let Ok(roles)=carvefoundry_core::analyze_compound_paths(&sources){
                for role in roles{
                    let title=match role.role{
                        carvefoundry_core::CompoundRole::Outline=>"Outline / island",
                        carvefoundry_core::CompoundRole::Hole=>"Hole / empty",
                    };
                    ui.small(format!("#{}: {} · depth {}",role.path_id,title,role.depth));
                }
            }
            ui.horizontal_wrapped(|ui|{
                if ui.button("Check cursor material")
                    .on_hover_text("Compute exact inside/outside Boolean parity for the last design cursor XY position. A point ON any boundary rejects; never a cutter clearance measurement.").clicked(){
                    match self.cursor_world {
                        Some(point)=>match self.editor.project.compound_material_at(region.id,point){
                            Ok(true)=>self.status=format!(
                                "Compound #{}: XY {:.3},{:.3} is material (even/odd CAD only)",
                                region.id,point.x,point.y),
                            Ok(false)=>self.status=format!(
                                "Compound #{}: XY {:.3},{:.3} is outside/void (CAD only)",
                                region.id,point.x,point.y),
                            Err(error)=>self.status=format!("Compound material check: {error}"),
                        },
                        None=>self.status="Move your pointer over the design canvas to establish an XY query".into(),
                    }
                }
                if ui.button("Remove saved region")
                    .on_hover_text("Forget compound source membership only; all editable source CAD vectors remain. One Undo restores membership.").clicked(){
                    self.apply(Action::RemoveCompoundRegion{id:region.id});
                }
            });
        }
        // Source-faithful closed-region Boolean ops. Only complete
        // non-touching/non-crossing analytic source boundaries can be
        // retained as the exact result; all others explicitly refuse.
        let saved=self.editor.project.compound_regions.clone();
        if saved.len()>=2{
            ui.separator();
            ui.strong("BOOLEAN CAD · EXACT NON-CROSSING REGIONS");
            ui.small("Choose two saved regions. Union, Intersection and A minus B retain complete original lines/arcs, with fresh editable source IDs and Undo. Crossing/touching/overlapping boundaries cannot yet be reconstructed and will be refused. No machining.");
            if !saved.iter().any(|r|r.id==self.topology_boolean_left){
                self.topology_boolean_left=saved[0].id;
            }
            if !saved.iter().any(|r|r.id==self.topology_boolean_right)
                || self.topology_boolean_left==self.topology_boolean_right{
                self.topology_boolean_right=saved.iter()
                    .find(|r|r.id!=self.topology_boolean_left)
                    .map_or(self.topology_boolean_left,|r|r.id);
            }
            ui.horizontal_wrapped(|ui|{
                ui.label("A");
                egui::ComboBox::from_id_salt("boolean-region-a")
                    .selected_text(saved.iter()
                        .find(|r|r.id==self.topology_boolean_left)
                        .map_or("Choose A".to_string(),|r|r.name.clone()))
                    .show_ui(ui,|ui|{
                        for region in &saved{
                            ui.selectable_value(&mut self.topology_boolean_left,
                                region.id,&region.name);
                        }
                    });
                ui.label("B");
                egui::ComboBox::from_id_salt("boolean-region-b")
                    .selected_text(saved.iter()
                        .find(|r|r.id==self.topology_boolean_right)
                        .map_or("Choose B".to_string(),|r|r.name.clone()))
                    .show_ui(ui,|ui|{
                        for region in &saved{
                            ui.selectable_value(&mut self.topology_boolean_right,
                                region.id,&region.name);
                        }
                    });
            });
            ui.horizontal_wrapped(|ui|{
                ui.label("Result");
                ui.text_edit_singleline(&mut self.topology_boolean_name);
            });
            let different=self.topology_boolean_left!=self.topology_boolean_right;
            ui.horizontal_wrapped(|ui|{
                for operation in [
                    carvefoundry_core::RegionBoolean::Union,
                    carvefoundry_core::RegionBoolean::Intersection,
                    carvefoundry_core::RegionBoolean::Difference,
                ]{
                    if ui.add_enabled(different,
                        egui::Button::new(operation.title()))
                        .on_hover_text("Exact, source-preserving result for provably disjoint or strictly nested saved CAD boundaries. Crossing, coincident, tangent, cubic or non-provable geometry rejects atomically. Difference means A minus B; not CNC toolpath generation.").clicked(){
                        let first_generated=self.editor.project.next_id;
                        self.apply(Action::BooleanRegions{
                            left_region_id:self.topology_boolean_left,
                            right_region_id:self.topology_boolean_right,
                            operation,name:self.topology_boolean_name.clone(),
                        });
                        if self.editor.project.paths.iter().any(|p|p.id==first_generated){
                            self.select_vector(Some(first_generated),false);
                        }
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
        ui.small("Exact offsets: straight contours, true circular arcs, and tangent line/arc chains. Mixed offsets also reject crossing/overlapping source and result edges. Rounded mode below supports convex circular joins and bounded concave circular trims. Cubic offsets remain unavailable.");
        if ui.add_enabled(eligible,egui::Button::new("Create offset vector"))
            .on_hover_text("Create a new independent analytic offset. Supports lines with bounded miters, true circular arcs, and tangent line/arc chains; all retained as original primitives. Open: + left / - right. Closed: + outward / - inward. Default offset mode rejects sharp curved corners. Use the separate Rounded offset for convex round joins and proven concave circular trims; cubic/overlapping sources remain unsupported.").clicked(){
            let newid=self.editor.project.next_id;
            self.apply(Action::OffsetLines{path_id,
                distance_mm:self.topology_distance_mm});
            if self.editor.project.paths.iter().any(|p|p.id==newid){
                self.select_vector(Some(newid),false);
            }
        }
        if ui.add_enabled(eligible,egui::Button::new("Create rounded offset"))
            .on_hover_text("EXPLICIT round-join mode: create true circular arcs on convex sharp corners and trim concave line/arc or arc/arc corners only where both offset segments meet within their original finite sweeps. No extrapolation. Open: + left / - right. Closed: + outward / - inward. Ambiguous intersections, collapsing geometry, overlaps and cubic offsets fail closed. CAD only, NOT machine toolpath clearance.").clicked(){
            let newid=self.editor.project.next_id;
            self.apply(Action::OffsetRounded{path_id,
                distance_mm:self.topology_distance_mm});
            if self.editor.project.paths.iter().any(|p|p.id==newid){
                self.select_vector(Some(newid),false);
            }
        }
        ui.small("Rounded offset: convex corners use true circular arcs; concave circular corners are trimmed only at one validated in-sweep crossing. Unresolvable joins show an error.");
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
        ui.small("Corners: line-line (open/closed). Exact mixed offsets validate the whole analytic contour; round/trim joins require the dedicated Rounded button.");
    }
}
fn curve_name(c:Curve)->&'static str{
    match c{Curve::Line=>"Line",Curve::Arc{..}=>"Circular arc",
        Curve::Cubic{..}=>"Cubic Bézier"}
}
