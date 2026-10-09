//! Large stock-centered 2D vector canvas, bounded rulers/grid, stable
//! first-press hit testing and direct drag behavior.
use super::super::{Studio,EditMode,ActiveDrag};
use carvefoundry_core::{Curve,Hit,PickMode,Point,movement_delta,pick,
    create_shape,shape_placement};
use eframe::egui;
use egui::{Color32,Pos2,Sense,Stroke,Vec2};
impl Studio {
    pub(crate) fn canvas(&mut self,ui:&mut egui::Ui) {
        ui.horizontal(|ui|{
            ui.strong("2D DESIGN");
            ui.separator();
            ui.label(format!("{} contours · {} analytic paths · {:.0}×{:.0} mm",
                self.editor.project.contours.len(),self.editor.project.paths.len(),
                self.editor.project.stock.width_mm,
                self.editor.project.stock.height_mm));
            ui.add(egui::Slider::new(&mut self.zoom,0.25..=8.0).text("Zoom"));
            if ui.button("Fit [F]").clicked(){
                self.zoom=1.0;self.pan=Vec2::ZERO;
            }
            ui.small("Wheel: zoom   Middle/right-drag: pan");
        });
        let size=ui.available_size().max(Vec2::splat(40.0));
        let (rect,response)=ui.allocate_exact_size(size,Sense::click_and_drag());
        // Navigation does not modify the design or its Undo history.
        let (mouse,wheel,pan_motion,pan_button)=ui.input(|i|(
            i.pointer.hover_pos(),i.smooth_scroll_delta.y,
            i.pointer.delta(),i.pointer.middle_down() || i.pointer.secondary_down()
        ));
        if let Some(mouse)=mouse && rect.contains(mouse) {
            if pan_button {self.pan+=pan_motion;}
            if wheel.abs()>0.05 {
                let before=self.zoom;
                self.zoom=(self.zoom*(wheel*0.002).exp()).clamp(0.25,8.0);
                let ratio=self.zoom/before;
                let relative=mouse-rect.center()-self.pan;
                self.pan+=relative*(1.0-ratio);
            }
        }
        let painter=ui.painter_at(rect);
        painter.rect_filled(rect,0.0,super::theme::CANVAS);
        let stock=&self.editor.project.stock;
        let scale=(((size.x-60.0)/stock.width_mm as f32)
            .min((size.y-60.0)/stock.height_mm as f32)).max(0.0001)*self.zoom;
        let origin=Pos2::new(
            rect.center().x+self.pan.x-stock.width_mm as f32*scale*0.5,
            rect.center().y+self.pan.y+stock.height_mm as f32*scale*0.5,
        );
        let screen=|p:Point|Pos2::new(
            origin.x+p.x as f32*scale,
            origin.y-p.y as f32*scale,
        );
        let back=egui::Rect::from_two_pos(screen(Point::new(0.,0.)),
            screen(Point::new(stock.width_mm,stock.height_mm)));
        painter.rect_filled(back,0.0,super::theme::STOCK);
        painter.rect_stroke(back,0.0,
            Stroke::new(2.0,Color32::from_rgb(141,128,112)),
            egui::StrokeKind::Inside);
        // Bounded rulers/grid; never emit tens of thousands of line shapes
        // for very large stock or at extreme zoom.
        let step=(10.0_f64)
            .max((stock.width_mm/80.0/10.0).ceil()*10.0)
            .max((stock.height_mm/80.0/10.0).ceil()*10.0);
        if self.show_grid && step*scale as f64>=3.0 {
            let count_x=(stock.width_mm/step) as usize;
            let count_y=(stock.height_mm/step) as usize;
            for i in 1..count_x.min(100){
                let x=i as f64*step;
                painter.line_segment([screen(Point::new(x,0.0)),
                    screen(Point::new(x,stock.height_mm))],
                    Stroke::new(0.65,super::theme::GRID));
            }
            for i in 1..count_y.min(100){
                let y=i as f64*step;
                painter.line_segment([screen(Point::new(0.0,y)),
                    screen(Point::new(stock.width_mm,y))],
                    Stroke::new(0.65,super::theme::GRID));
            }
        }
        if step*scale as f64>=14.0 {
            for i in 0..=((stock.width_mm/step) as usize).min(100){
                let x=i as f64*step;
                painter.text(screen(Point::new(x,0.0))+Vec2::new(0.0,8.0),
                    egui::Align2::CENTER_TOP,format!("{x:.0}"),
                    egui::FontId::monospace(10.0),super::theme::MUTED);
            }
            for i in 0..=((stock.height_mm/step) as usize).min(100){
                let y=i as f64*step;
                painter.text(screen(Point::new(0.0,y))+Vec2::new(-9.0,0.0),
                    egui::Align2::RIGHT_CENTER,format!("{y:.0}"),
                    egui::FontId::monospace(10.0),super::theme::MUTED);
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
                    if chosen{super::theme::SELECTION}
                    else{super::theme::VECTOR})));
        }
        for path in &self.editor.project.paths {
            if !path.visible {continue;}
            let Ok(polyline)=path.preview_points(0.3) else {continue;};
            let chosen=self.selected_path==Some(path.id);
            let style=Stroke::new(if chosen{2.6}else{1.6},
                if chosen{super::theme::SELECTION}
                else{super::theme::VECTOR});
            let points:Vec<Pos2>=polyline.into_iter().map(&screen).collect();
            if path.closed {painter.add(egui::Shape::closed_line(points,style));}
            else{painter.add(egui::Shape::line(points,style));}
            if self.edit_mode==EditMode::Nodes {
                for (i,node) in path.nodes.iter().enumerate() {
                    let at=screen(node.position.offset(path.origin.x,path.origin.y));
                    painter.circle_filled(at,
                        if chosen && Some(node.id)==self.selected_node{6.5}else{4.0},
                        if chosen && Some(node.id)==self.selected_node {
                            Color32::WHITE
                        }else if chosen{
                            super::theme::SELECTION
                        }else{
                            Color32::from_rgb(72,137,174)
                        });
                    if chosen{
                        painter.text(at+Vec2::new(7.0,-6.0),egui::Align2::LEFT_BOTTOM,
                            format!("{}",node.id),egui::FontId::monospace(10.0),
                            Color32::WHITE);
                    }
                    if chosen && let Some(segment)=path.segments.get(i){
                        match segment.curve {
                            Curve::Cubic{control1,control2} => {
                                let start=node.position.offset(path.origin.x,path.origin.y);
                                let end=path.nodes[(i+1)%path.nodes.len()]
                                    .position.offset(path.origin.x,path.origin.y);
                                for (control,from,handle) in [
                                    (control1,start,1_u8),(control2,end,2_u8),
                                ] {
                                    let world=control.offset(path.origin.x,path.origin.y);
                                    let pos=screen(world);
                                    painter.line_segment([screen(from),pos],
                                        Stroke::new(0.8,Color32::from_rgb(150,167,196)));
                                    painter.circle_filled(pos,
                                        if self.selected_handle==Some((segment.id,handle)){6.0}else{4.0},
                                        Color32::from_rgb(255,130,174));
                                }
                            }
                            Curve::Arc{center,..} => {
                                painter.circle_stroke(
                                    screen(center.offset(path.origin.x,path.origin.y)),
                                    3.0,Stroke::new(1.0,Color32::from_rgb(140,153,180)));
                            }
                            Curve::Line=>{}
                        }
                    }
                }
            }
        }
        painter.text(screen(Point::new(0.,0.))+Vec2::new(6.,6.),
            egui::Align2::LEFT_TOP,"XY0",
            egui::FontId::monospace(12.),Color32::from_rgb(40,50,60));
        let pointer=response.interact_pointer_pos();
        let to_world=|p:Pos2|Point::new(
            (p.x-origin.x) as f64/scale as f64,
            (origin.y-p.y) as f64/scale as f64,
        );
        // Press-origin hit-testing is essential. The pointer may already have
        // moved >10px by egui::Response::drag_started(), so hover hits miss.
        let radius=9.0/scale as f64;
        let pointer_world=pointer.map(to_world);
        self.cursor_world=pointer_world.filter(|p|p.finite());
        let pressed=ui.input(|i|i.pointer.press_origin())
            .filter(|p|rect.contains(*p)).map(to_world);
        let pick_mode=if self.edit_mode==EditMode::Nodes{
            PickMode::Nodes
        }else{PickMode::Objects};
        let click_target=pointer_world.and_then(|p|
            pick(&self.editor.project,p,radius,pick_mode));
        let press_target=pressed.and_then(|p|
            pick(&self.editor.project,p,radius,pick_mode));

        // A shape tool creates one object per mouse gesture. Until release,
        // the project/Undo history are completely unchanged.
        if let Some(kind)=self.active_shape {
            if response.drag_started() && ui.input(|i|i.pointer.primary_down()) {
                self.shape_drag_start=ui.input(|i|i.pointer.press_origin())
                    .filter(|at|back.contains(*at)).map(to_world);
                self.shape_drag_delta=None;
                if self.shape_drag_start.is_none(){
                    self.status="Start drawing inside the material outline".into();
                }
            }
            if let Some(start)=self.shape_drag_start {
                let delta=response.drag_delta();
                let snapped=movement_delta(delta.x as f64/scale as f64,
                    -delta.y as f64/scale as f64,
                    if self.use_grid{Some(self.grid_step)}else{None});
                let square=ui.input(|i|i.modifiers.shift);
                if response.dragged(){
                    self.shape_drag_delta=Some(snapped);
                }
                let final_delta=if response.drag_stopped(){
                    self.shape_drag_delta.take().unwrap_or(snapped)
                }else{snapped};
                if let Ok(placement)=shape_placement(start,final_delta,kind,square){
                    if let Ok(preview)=create_shape(1,"Draft".into(),placement.origin,
                        kind,placement.width_mm,placement.height_mm){
                        if let Ok(outline)=preview.preview_points(0.4){
                            let points:Vec<Pos2>=outline.into_iter().map(screen).collect();
                            painter.add(egui::Shape::closed_line(points,
                                Stroke::new(2.0,super::theme::SELECTION)));
                            let top=screen(Point::new(placement.origin.x,
                                placement.origin.y+placement.height_mm));
                            painter.text(top+Vec2::new(6.0,-8.0),
                                egui::Align2::LEFT_BOTTOM,
                                format!("{:.2} × {:.2} mm",
                                    placement.width_mm,placement.height_mm),
                                egui::FontId::monospace(12.0),super::theme::SELECTION);
                        }
                    }
                }
                if response.drag_stopped() {
                    self.shape_drag_start=None;
                    match shape_placement(start,final_delta,kind,square){
                        Ok(placement)=>self.create_drag_shape(kind,placement),
                        Err(error)=>self.status=format!("No shape created: {error}"),
                    }
                }
            }else if response.clicked() {
                self.status=format!("{} selected: drag a diagonal on the stock to place it.",
                    kind.title());
            }
        }else if self.edit_mode==EditMode::Draw {
            if response.double_clicked(){
                self.finish_drawing();
            }else if response.clicked() && let Some(mut at)=pointer_world {
                if self.use_grid && (0.1..=100.0).contains(&self.grid_step){
                    at.x=(at.x/self.grid_step).round()*self.grid_step;
                    at.y=(at.y/self.grid_step).round()*self.grid_step;
                }
                if at.finite() && self.drawing.last().is_none_or(|p|
                    (p.x-at.x).hypot(p.y-at.y)>0.001){
                    self.drawing.push(at);
                }
            }
        }else{
            if response.clicked() {
                self.apply_canvas_hit(click_target);
            }
            if response.drag_started() && ui.input(|i|i.pointer.primary_down()) {
                let result=match press_target {
                    Some(Hit::Node{path_id,node_id}) if self.edit_mode==EditMode::Nodes=>{
                        self.selected_path=Some(path_id);
                        self.selected=None;
                        self.selected_node=Some(node_id);
                        self.selected_handle=None;
                        self.editor.start_node_drag(path_id,node_id)
                            .map(|at|ActiveDrag::Node(path_id,node_id,at))
                    }
                    Some(Hit::Handle{path_id,segment_id,handle})
                        if self.edit_mode==EditMode::Nodes=>{
                        self.selected_path=Some(path_id);
                        self.selected=None;
                        self.selected_node=None;
                        self.selected_handle=Some((segment_id,handle));
                        self.editor.start_control_drag(path_id,segment_id,handle)
                            .map(|at|ActiveDrag::Control(path_id,segment_id,handle,at))
                    }
                    Some(Hit::Path(id)) if self.edit_mode==EditMode::Objects=>{
                        self.selected_path=Some(id);self.selected=None;
                        self.selected_node=None;self.selected_handle=None;
                        self.editor.start_path_drag(id)
                            .map(|at|ActiveDrag::Path(id,at))
                    }
                    Some(Hit::Contour(id)) if self.edit_mode==EditMode::Objects=>{
                        self.selected_path=None;self.selected=Some(id);
                        self.selected_node=None;self.selected_handle=None;
                        self.editor.start_drag(id)
                            .map(|at|ActiveDrag::Contour(id,at))
                    }
                    other=>{
                        self.apply_canvas_hit(other);
                        Ok(ActiveDrag::None)
                    }
                };
                match result{
                    Ok(ActiveDrag::None)=>self.drag=None,
                    Ok(target)=>self.drag=Some(target),
                    Err(error)=>{
                        self.drag=None;
                        self.status=format!("Cannot drag: {error}");
                    }
                }
            }
            if response.dragged() && let Some(drag)=self.drag {
                let delta=response.drag_delta();
                let shift=movement_delta(delta.x as f64/scale as f64,
                    -delta.y as f64/scale as f64,
                    if self.use_grid{Some(self.grid_step)}else{None});
                let result=match drag {
                    ActiveDrag::Contour(id,start)=>self.editor.preview_drag(
                        id,start.offset(shift.x,shift.y)),
                    ActiveDrag::Path(id,start)=>self.editor.preview_path_drag(
                        id,start.offset(shift.x,shift.y)),
                    ActiveDrag::Node(id,node,start)=>self.editor.preview_node_drag(
                        id,node,start.offset(shift.x,shift.y)),
                    ActiveDrag::Control(id,seg,handle,start)=>
                        self.editor.preview_control_drag(id,seg,handle,
                            start.offset(shift.x,shift.y)),
                    ActiveDrag::None=>Ok(()),
                };
                if let Err(error)=result{
                    self.status=format!("Movement rejected: {error}");
                }
            }
            if response.drag_stopped() {
                self.editor.finish_drag();
                self.drag=None;
            }
        }
        // Draw draft geometry as distinct temporary guides; never autosave
        // uncommitted pen clicks into the actual design project.
        if self.edit_mode==EditMode::Draw {
            let mut points:Vec<Pos2>=self.drawing.iter().copied().map(screen).collect();
            if let Some(here)=pointer && rect.contains(here){
                points.push(here);
            }
            if points.len()>=2 {
                painter.add(egui::Shape::line(points,
                    Stroke::new(2.0,Color32::from_rgb(255,200,86))));
            }
            for p in &self.drawing {
                painter.circle_filled(screen(*p),4.0,Color32::WHITE);
            }
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
