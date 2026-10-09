//! Font-independent vector icons for the native editor.
use eframe::egui;

#[derive(Clone,Copy)]
pub(crate) enum Icon { Rectangle, Circle, Star, Arc, Eye, Hidden, Lock, Unlock, Left, Right, Up, Down }

pub(crate) fn button(ui:&mut egui::Ui,label:&str,tip:&str,icon:Icon,width:f32)->egui::Response{
    let r=ui.add_sized([width,29.0],egui::Button::new(format!("    {label}"))).on_hover_text(tip);
    draw(ui.painter(),r.rect.left_center()+egui::vec2(14.0,0.0),icon);
    r
}
pub(crate) fn small(ui:&mut egui::Ui,tip:&str,icon:Icon)->egui::Response{
    let r=ui.add_sized([29.0,26.0],egui::Button::new(" ")).on_hover_text(tip);
    draw(ui.painter(),r.rect.center(),icon);
    r
}
fn draw(p:&egui::Painter,c:egui::Pos2,icon:Icon){
    let st=egui::Stroke::new(1.5,egui::Color32::LIGHT_BLUE);
    let pt=|x:f32,y:f32|egui::pos2(c.x+x,c.y+y);
    let ln=|x:f32,y:f32,a:f32,b:f32|{p.line_segment([pt(x,y),pt(a,b)],st);};
    match icon{
        Icon::Rectangle=>{ln(-6.0,-5.0,6.0,-5.0);ln(6.0,-5.0,6.0,5.0);ln(6.0,5.0,-6.0,5.0);ln(-6.0,5.0,-6.0,-5.0);}
        Icon::Circle=>{p.circle_stroke(c,6.0,st);}
        Icon::Star=>{ln(-7.0,2.0,7.0,2.0);ln(7.0,2.0,-4.0,-6.0);ln(-4.0,-6.0,0.0,7.0);ln(0.0,7.0,4.0,-6.0);ln(4.0,-6.0,-7.0,2.0);}
        Icon::Arc=>{let v=(0..=16).map(|i|{let a=i as f32*std::f32::consts::PI/16.0;pt(-7.0*a.cos(),-5.0*a.sin())}).collect();p.add(egui::Shape::line(v,st));}
        Icon::Eye|Icon::Hidden=>{p.circle_stroke(c,5.0,st);p.circle_filled(c,2.0,st.color);if matches!(icon,Icon::Hidden){ln(-7.0,7.0,7.0,-7.0);}}
        Icon::Lock|Icon::Unlock=>{ln(-5.0,-1.0,5.0,-1.0);ln(5.0,-1.0,5.0,7.0);ln(5.0,7.0,-5.0,7.0);ln(-5.0,7.0,-5.0,-1.0);let x=if matches!(icon,Icon::Lock){-4.0}else{1.0};ln(x,-1.0,x,-7.0);ln(x,-7.0,x+5.0,-7.0);}
        Icon::Left=>{ln(6.0,0.0,-6.0,0.0);ln(-6.0,0.0,-1.0,-5.0);ln(-6.0,0.0,-1.0,5.0);}
        Icon::Right=>{ln(-6.0,0.0,6.0,0.0);ln(6.0,0.0,1.0,-5.0);ln(6.0,0.0,1.0,5.0);}
        Icon::Up=>{ln(0.0,6.0,0.0,-6.0);ln(0.0,-6.0,-5.0,-1.0);ln(0.0,-6.0,5.0,-1.0);}
        Icon::Down=>{ln(0.0,-6.0,0.0,6.0);ln(0.0,6.0,-5.0,1.0);ln(0.0,6.0,5.0,1.0);}
    }
}
