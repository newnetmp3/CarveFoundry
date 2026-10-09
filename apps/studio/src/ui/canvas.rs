//! Large stock-centered 2D vector canvas, bounded rulers/grid, stable
//! first-press hit testing and direct drag behavior.
use super::super::{Studio,EditMode,ActiveDrag};
use carvefoundry_core::{Curve,Hit,PickMode,Point,movement_delta,pick,
    nearest_snap,marquee_ids,SnapKind,
    create_shape,shape_placement};
use eframe::egui;
use egui::{Color32,Pos2,Sense,Stroke,Vec2};
/// Return displacement from the INITIAL pointer press, not one frame of mouse motion.
/// egui Response::drag_delta is a *per-frame* delta and must never drive an
/// Editor preview that rebuilds geometry from its pre-drag snapshot.
fn total_drag_world(response:&egui::Response,scale:f32,grid:Option<f64>)->Point {
    let total=response.total_drag_delta().unwrap_or_default();
    cumulative_drag_world(total,scale,grid)
}

fn cumulative_drag_world(total:Vec2,scale:f32,grid:Option<f64>)->Point {
    movement_delta(total.x as f64/scale as f64,
        -total.y as f64/scale as f64,grid)
}

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
            if ui.add_enabled(!self.selected_ids.is_empty(),
                egui::Button::new("Fit selection [Shift+F]"))
                .on_hover_text("Zoom and center the selected geometry without changing project coordinates")
                .clicked(){self.fit_selection();}
            ui.small("Wheel: zoom   Middle/right-drag: pan");
        });
        let size=ui.available_size().max(Vec2::splat(40.0));
        self.canvas_size=size;
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
            let chosen=self.selected_ids.contains(&part.id);
            painter.add(egui::Shape::closed_line(points,
                Stroke::new(if chosen{2.5}else{1.5},
                    if chosen{super::theme::SELECTION}
                    else{super::theme::VECTOR})));
        }
        for path in &self.editor.project.paths {
            if !path.visible {continue;}
            let Ok(polyline)=path.preview_points(0.3) else {continue;};
            let chosen=self.selected_ids.contains(&path.id);
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
        // Selection envelope reflects exact analytic arcs/Bézier extrema,
        // not the coarse on-screen path sampling. Purely visual; no resize
        // handles are shown until a proper validated resize tool exists.
        if self.edit_mode==EditMode::Objects
            && let Some((low,high))=self.selection_envelope(){
            let outline=egui::Rect::from_two_pos(screen(low),screen(high));
            painter.rect_stroke(outline,0.0,Stroke::new(1.25,super::theme::SELECTION),
                egui::StrokeKind::Outside);
            let caption=format!("{} selected  ·  {:.2} × {:.2} mm",
                self.selected_ids.len(),high.x-low.x,high.y-low.y);
            let label=screen(Point::new(low.x,high.y))+Vec2::new(1.0,-8.0);
            painter.text(label,egui::Align2::LEFT_BOTTOM,caption,
                egui::FontId::monospace(11.0),super::theme::SELECTION);
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

        let snap_suppressed=ui.input(|i|i.modifiers.alt);
        let editing_path=self.drag.as_ref().and_then(|drag|match drag{
            ActiveDrag::Node(id,..)|ActiveDrag::Control(id,..)=>Some(*id),
            _=>None,
        });
        let exclusions:Vec<u64>=editing_path.into_iter().collect();
        if self.snap_features && !snap_suppressed
            && let Some(world)=pointer_world
            && let Some(snap)=nearest_snap(&self.editor.project,
                world,10.0/scale as f64,&exclusions){
            let target=screen(snap.point);
            painter.circle_stroke(target,7.0,Stroke::new(1.6,super::theme::SELECTION));
            painter.line_segment([target+Vec2::new(-4.0,0.0),
                target+Vec2::new(4.0,0.0)],
                Stroke::new(1.0,super::theme::SELECTION));
            let name=match snap.kind{
                SnapKind::Vertex=>"Endpoint",
                SnapKind::Midpoint=>"Midpoint",
                SnapKind::StockCorner=>"Stock corner",
            };
            painter.text(target+Vec2::new(9.0,-8.0),egui::Align2::LEFT_BOTTOM,
                name,egui::FontId::monospace(10.0),super::theme::SELECTION);
        }

        // A shape tool creates one object per mouse gesture. Until release,
        // the project/Undo history are completely unchanged.
        if let Some(kind)=self.active_shape {
            if self.exact_shape_placement {
                let width=if kind==carvefoundry_core::ShapeKind::Circle {
                    self.shape_width.min(self.shape_height)
                }else{self.shape_width};
                let height=if kind==carvefoundry_core::ShapeKind::Circle {
                    width
                }else{self.shape_height};
                if let Some(cursor)=response.hover_pos()
                    && back.contains(cursor) {
                    let mut at=to_world(cursor);
                    if self.snap_features
                        && let Some(snap)=nearest_snap(&self.editor.project,
                            at,10.0/scale as f64,&[]){at=snap.point;}
                    if let Ok(preview)=create_shape(1,"Draft".into(),at,
                        kind,width,height)
                        && let Ok(polyline)=preview.preview_points(0.4) {
                        let screen_points:Vec<Pos2>=polyline.into_iter().map(screen).collect();
                        painter.add(egui::Shape::closed_line(screen_points,
                            Stroke::new(1.3,super::theme::SELECTION)));
                    }
                }
                if response.clicked() && let Some(cursor)=pointer
                    && back.contains(cursor) {
                    let mut at=to_world(cursor);
                    if self.snap_features
                        && let Some(snap)=nearest_snap(&self.editor.project,
                            at,10.0/scale as f64,&[]){at=snap.point;}
                    self.create_drag_shape(kind,carvefoundry_core::ShapePlacement{
                        origin:at,width_mm:width,height_mm:height,
                    });
                }
            }else{
            if response.drag_started() && ui.input(|i|i.pointer.primary_down()) {
                self.shape_drag_start=ui.input(|i|i.pointer.press_origin())
                    .filter(|at|back.contains(*at)).map(to_world)
                    .map(|at|if self.snap_features{
                        nearest_snap(&self.editor.project,at,10.0/scale as f64,&[])
                            .map_or(at,|snap|snap.point)
                    }else{at});
                self.shape_drag_delta=None;
                if self.shape_drag_start.is_none(){
                    self.status="Start drawing inside the material outline".into();
                }
            }
            if let Some(start)=self.shape_drag_start {
                let snapped=total_drag_world(&response,scale,
                    if self.use_grid{Some(self.grid_step)}else{None});
                let square=ui.input(|i|i.modifiers.shift);
                if response.dragged(){
                    self.shape_drag_delta=Some(snapped);
                }
                let final_delta=if response.drag_stopped(){
                    self.shape_drag_delta.take().unwrap_or(snapped)
                }else{snapped};
                if let Ok(placement)=shape_placement(start,final_delta,kind,square)
                    && let Ok(preview)=create_shape(1,"Draft".into(),placement.origin,
                        kind,placement.width_mm,placement.height_mm)
                    && let Ok(outline)=preview.preview_points(0.4) {
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
            }
        }else if self.edit_mode==EditMode::Draw {
            if response.double_clicked(){
                self.finish_drawing();
            }else if response.clicked() && let Some(mut at)=pointer_world {
                let feature_snap=if self.snap_features{
                    nearest_snap(&self.editor.project,at,10.0/scale as f64,&[])
                }else{None};
                if let Some(snap)=feature_snap{at=snap.point;}
                else if self.use_grid && (0.1..=100.0).contains(&self.grid_step){
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
                let additive=ui.input(|i|i.modifiers.shift || i.modifiers.command);
                self.apply_canvas_hit(click_target,additive);
            }
            if response.drag_started() && ui.input(|i|i.pointer.primary_down()) {
                let selection_extend=ui.input(|i|i.modifiers.shift || i.modifiers.command);
                let hit_id=match press_target{
                    Some(Hit::Path(id))|Some(Hit::Contour(id))=>Some(id),
                    _=>None,
                };
                let result=if let Some(id)=hit_id
                    && !selection_extend
                    && self.selected_ids.len()>1
                    && self.selected_ids.contains(&id)
                    && self.edit_mode==EditMode::Objects{
                    let ids:Vec<u64>=self.selected_ids.iter().copied().collect();
                    self.editor.start_group_drag(&ids)
                        .map(|()|ActiveDrag::Group(ids))
                }else{match press_target {
                    Some(Hit::Node{path_id,node_id}) if self.edit_mode==EditMode::Nodes=>{
                        self.select_vector(Some(path_id),false);
                        self.selected_node=Some(node_id);
                        self.selected_handle=None;
                        self.editor.start_node_drag(path_id,node_id)
                            .map(|at|ActiveDrag::Node(path_id,node_id,at))
                    }
                    Some(Hit::Handle{path_id,segment_id,handle})
                        if self.edit_mode==EditMode::Nodes=>{
                        self.select_vector(Some(path_id),false);
                        self.selected_node=None;
                        self.selected_handle=Some((segment_id,handle));
                        self.editor.start_control_drag(path_id,segment_id,handle)
                            .map(|at|ActiveDrag::Control(path_id,segment_id,handle,at))
                    }
                    Some(Hit::Path(id)) if self.edit_mode==EditMode::Objects=>{
                        self.select_vector(Some(id),false);
                        self.editor.start_path_drag(id)
                            .map(|at|ActiveDrag::Path(id,at))
                    }
                    Some(Hit::Contour(id)) if self.edit_mode==EditMode::Objects=>{
                        self.select_vector(Some(id),false);
                        self.editor.start_drag(id)
                            .map(|at|ActiveDrag::Contour(id,at))
                    }
                    other=>{
                        if self.edit_mode==EditMode::Objects
                            && other.is_none(){
                            self.marquee_start=pressed;
                            self.marquee_extend=selection_extend;
                        }else if !selection_extend{
                            self.apply_canvas_hit(other,false);
                        }
                        Ok(ActiveDrag::None)
                    }
                }};
                match result{
                    Ok(ActiveDrag::None)=>self.drag=None,
                    Ok(target)=>self.drag=Some(target),
                    Err(error)=>{
                        self.drag=None;
                        self.status=format!("Cannot drag: {error}");
                    }
                }
            }
            if response.dragged() && let Some(drag)=self.drag.clone() {
                let shift=total_drag_world(&response,scale,
                    if self.use_grid{Some(self.grid_step)}else{None});
                let result=match drag {
                    ActiveDrag::Group(ids)=>self.editor.preview_group_drag(&ids,shift),
                    ActiveDrag::Contour(id,start)=>self.editor.preview_drag(
                        id,start.offset(shift.x,shift.y)),
                    ActiveDrag::Path(id,start)=>self.editor.preview_path_drag(
                        id,start.offset(shift.x,shift.y)),
                    ActiveDrag::Node(id,node,start)=>{
                        let mut position=start.offset(shift.x,shift.y);
                        if self.snap_features && !snap_suppressed
                            && let Some(path)=self.editor.project.paths.iter()
                                .find(|p|p.id==id){
                            let world=position.offset(path.origin.x,path.origin.y);
                            if let Some(snap)=nearest_snap(&self.editor.project,
                                world,10.0/scale as f64,&[id]){
                                position=Point::new(snap.point.x-path.origin.x,
                                    snap.point.y-path.origin.y);
                            }
                        }
                        self.editor.preview_node_drag(id,node,position)
                    }
                    ActiveDrag::Control(id,seg,handle,start)=>{
                        let mut position=start.offset(shift.x,shift.y);
                        if self.snap_features && !snap_suppressed
                            && let Some(path)=self.editor.project.paths.iter()
                                .find(|p|p.id==id){
                            let world=position.offset(path.origin.x,path.origin.y);
                            if let Some(snap)=nearest_snap(&self.editor.project,
                                world,10.0/scale as f64,&[id]){
                                position=Point::new(snap.point.x-path.origin.x,
                                    snap.point.y-path.origin.y);
                            }
                        }
                        self.editor.preview_control_drag(id,seg,handle,position)
                    },
                    ActiveDrag::None=>Ok(()),
                };
                if let Err(error)=result{
                    self.status=format!("Movement rejected: {error}");
                }
            }
            if response.drag_stopped() {
                self.editor.finish_drag();
                self.drag=None;
                if let Some(start)=self.marquee_start.take()
                    && let Some(end)=pointer_world{
                    let found=marquee_ids(&self.editor.project,start,end);
                    if !self.marquee_extend{self.select_vector(None,false);}
                    for id in found{self.selected_ids.insert(id);}
                    self.reconcile_selection();
                    self.status=format!("{} vectors selected",self.selected_ids.len());
                }
            }
        }
        if let Some(start)=self.marquee_start
            && let Some(end)=pointer_world {
            let a=screen(start);
            let b=screen(end);
            painter.rect_stroke(egui::Rect::from_two_pos(a,b),0.0,
                Stroke::new(1.0,super::theme::SELECTION),
                egui::StrokeKind::Inside);
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

#[cfg(test)]
mod drag_regression_tests {
    use super::*;

    #[test]
    fn cumulative_pointer_motion_is_not_each_frames_motion() {
        // A slow pointer can move ~2px/frame but end up 84px from its
        // press point. Absolute preview commands MUST see the 84px.
        let screen_totals=[
            Vec2::new(2.0,-1.0),
            Vec2::new(32.0,-12.0),
            Vec2::new(84.0,-36.0),
            Vec2::new(84.0,-36.0), // stationary frame must not reset shape
        ];
        let positions:Vec<_>=screen_totals.into_iter()
            .map(|total|cumulative_drag_world(total,2.0,None)).collect();
        assert_eq!(positions[0],Point::new(1.0,0.5));
        assert_eq!(positions[1],Point::new(16.0,6.0));
        assert_eq!(positions[2],Point::new(42.0,18.0));
        assert_eq!(positions[3],positions[2]);
    }

    #[test]
    fn cumulative_node_drag_is_one_undoable_edit() {
        use carvefoundry_core::{Action,Editor,ShapeKind};
        let mut editor=Editor::default();
        editor.apply(Action::AddShape{
            kind:ShapeKind::Rectangle,name:"Test".into(),
            origin:Point::new(20.0,20.0),
            width_mm:40.0,height_mm:30.0,
        }).unwrap();
        let initial=editor.project.clone();
        let node_id=editor.project.paths[0].nodes[0].id;
        let start=editor.start_node_drag(1,node_id).unwrap();

        for total in [Vec2::new(4.0,-2.0),
            Vec2::new(30.0,-20.0),Vec2::new(30.0,-20.0)] {
            let delta=cumulative_drag_world(total,2.0,None);
            editor.preview_node_drag(1,node_id,
                start.offset(delta.x,delta.y)).unwrap();
        }
        assert_eq!(editor.project.paths[0].nodes[0].position,
            start.offset(15.0,10.0));
        editor.finish_drag();
        assert!(editor.undo());
        assert_eq!(editor.project,initial);
        assert!(!editor.can_undo());
    }

    #[test]
    fn cumulative_whole_vector_drag_uses_complete_distance() {
        use carvefoundry_core::{Action,Editor,ShapeKind};
        let mut editor=Editor::default();
        editor.apply(Action::AddShape{
            kind:ShapeKind::Rectangle,name:"Test".into(),
            origin:Point::new(20.0,20.0),
            width_mm:40.0,height_mm:30.0,
        }).unwrap();
        let initial=editor.project.clone();
        let start=editor.start_path_drag(1).unwrap();
        for total in [Vec2::new(5.0,0.0),Vec2::new(50.0,20.0)] {
            let delta=cumulative_drag_world(total,2.0,None);
            editor.preview_path_drag(1,start.offset(delta.x,delta.y))
                .unwrap();
        }
        assert_eq!(editor.project.paths[0].origin,Point::new(45.0,10.0));
        editor.finish_drag();
        assert!(editor.undo());
        assert_eq!(editor.project,initial);
    }

    #[test]
    fn snapped_total_drag_preserves_sub_grid_press_origin() {
        let start=Point::new(35.75,70.125);
        let motion=cumulative_drag_world(Vec2::new(53.0,-19.0),
            2.0,Some(5.0));
        assert_eq!(motion,Point::new(25.0,10.0));
        assert_eq!(start.offset(motion.x,motion.y),
            Point::new(60.75,80.125));
    }
}
