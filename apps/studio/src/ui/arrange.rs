//! Practical CNC vector arrangement controls: precise placement, alignment,
//! spacing and one-step keyboard nudges. No project mutations during typing.
use super::super::Studio;
use carvefoundry_core::{Arrangement,Point,vector_bounds};
use eframe::egui;

impl Studio{
    pub(crate) fn selection_envelope(&self)->Option<(Point,Point)>{
        let mut lo=Point::new(f64::INFINITY,f64::INFINITY);
        let mut hi=Point::new(f64::NEG_INFINITY,f64::NEG_INFINITY);
        for id in &self.selected_ids{
            let Ok(bounds)=vector_bounds(&self.editor.project,*id)else{return None;};
            lo.x=lo.x.min(bounds.min.x);
            lo.y=lo.y.min(bounds.min.y);
            hi.x=hi.x.max(bounds.max.x);
            hi.y=hi.y.max(bounds.max.y);
        }
        lo.x.is_finite().then_some((lo,hi))
    }
    /// When a selection changes, initialize numeric placement from the
    /// genuine lower-left vector envelope, not current object origins.
    fn ensure_precision_reference(&mut self){
        let selected=self.selected_vector_ids();
        if self.precise_selection!=selected{
            self.precise_selection=selected;
            if let Some((lo,_))=self.selection_envelope(){
                self.precise_x=lo.x;
                self.precise_y=lo.y;
            }
        }
    }
    pub(crate) fn precise_tools(&mut self,ui:&mut egui::Ui){
        let count=self.selected_ids.len();
        let one_or_more=count>=1;
        let two_or_more=count>=2;
        let three_or_more=count>=3;
        ui.label(egui::RichText::new("PRECISION POSITION")
            .strong().color(super::theme::ACCENT));
        ui.group(|ui|{
            self.ensure_precision_reference();
            if let Some((low,high))=self.selection_envelope(){
                ui.small(format!("{} selected · X {:.2}..{:.2} · Y {:.2}..{:.2} mm",
                    count,low.x,high.x,low.y,high.y));
                ui.horizontal_wrapped(|ui|{
                    ui.label("Left X");
                    ui.add(egui::DragValue::new(&mut self.precise_x)
                        .speed(0.1).suffix(" mm"));
                    ui.label("Bottom Y");
                    ui.add(egui::DragValue::new(&mut self.precise_y)
                        .speed(0.1).suffix(" mm"));
                });
                ui.horizontal_wrapped(|ui|{
                    if ui.button("Set X/Y").on_hover_text(
                        "Move the entire selection so its left/bottom bounds match the coordinates"
                    ).clicked(){
                        self.move_selection(Point::new(self.precise_x-low.x,
                            self.precise_y-low.y));
                    }
                    if ui.button("Read position").on_hover_text(
                        "Discard draft fields and read the current selection position"
                    ).clicked(){
                        self.precise_x=low.x;self.precise_y=low.y;
                    }
                });
            }else{
                ui.weak("Select a vector to place it at exact XY coordinates.");
            }
            ui.separator();
            ui.horizontal_wrapped(|ui|{
                ui.label("Step");
                ui.add(egui::DragValue::new(&mut self.nudge_mm)
                    .range(0.01..=1000.0).speed(0.05).suffix(" mm"));
            });
            let nudge=self.nudge_mm;
            ui.horizontal_wrapped(|ui|{
                if ui.add_enabled(one_or_more,egui::Button::new("←")).clicked(){
                    self.move_selection(Point::new(-nudge,0.0));
                }
                if ui.add_enabled(one_or_more,egui::Button::new("→")).clicked(){
                    self.move_selection(Point::new(nudge,0.0));
                }
                if ui.add_enabled(one_or_more,egui::Button::new("↑")).clicked(){
                    self.move_selection(Point::new(0.0,nudge));
                }
                if ui.add_enabled(one_or_more,egui::Button::new("↓")).clicked(){
                    self.move_selection(Point::new(0.0,-nudge));
                }
            });
            ui.small("Arrow keys: nudge one step · Shift+arrow: 10 steps");
        });
        ui.add_space(6.0);
        ui.label(egui::RichText::new("ALIGN SELECTED VECTORS")
            .strong().color(super::theme::ACCENT));
        ui.group(|ui|{
            ui.small("Two or more selected vectors. Align each to the selection's bounding edges or centers.");
            ui.horizontal_wrapped(|ui|{
                for (label,mode,tip) in [
                    ("Left",Arrangement::Left,"Align left edges"),
                    ("Center X",Arrangement::HCenter,"Align horizontal centers"),
                    ("Right",Arrangement::Right,"Align right edges"),
                    ("Bottom",Arrangement::Bottom,"Align bottom edges"),
                    ("Center Y",Arrangement::VCenter,"Align vertical centers"),
                    ("Top",Arrangement::Top,"Align top edges"),
                ]{
                    if ui.add_enabled(two_or_more,egui::Button::new(label))
                        .on_hover_text(tip).clicked(){self.arrange_selection(mode);}
                }
            });
            ui.separator();
            ui.horizontal_wrapped(|ui|{
                if ui.add_enabled(three_or_more,egui::Button::new("Space X evenly"))
                    .on_hover_text("Equalize gaps between the object centers; keep outermost centers fixed").clicked(){
                    self.arrange_selection(Arrangement::DistributeX);
                }
                if ui.add_enabled(three_or_more,egui::Button::new("Space Y evenly"))
                    .on_hover_text("Equalize gaps between the object centers; keep outermost centers fixed").clicked(){
                    self.arrange_selection(Arrangement::DistributeY);
                }
            });
            if count<3{ui.weak("Even spacing requires 3 or more vectors.");}
        });
        ui.add_space(6.0);
        ui.label(egui::RichText::new("PLACE GROUP ON MATERIAL")
            .strong().color(super::theme::ACCENT));
        ui.group(|ui|{
            ui.small("Keep the selected vectors' spacing; move their combined bounds to stock edges or center.");
            ui.horizontal_wrapped(|ui|{
                for (label,mode) in [
                    ("Left edge",Arrangement::StockLeft),
                    ("Center X",Arrangement::StockHCenter),
                    ("Right edge",Arrangement::StockRight),
                    ("Bottom edge",Arrangement::StockBottom),
                    ("Center Y",Arrangement::StockVCenter),
                    ("Top edge",Arrangement::StockTop),
                ]{
                    if ui.add_enabled(one_or_more,egui::Button::new(label))
                        .on_hover_text(mode.title()).clicked(){
                        self.arrange_selection(mode);
                    }
                }
            });
        });
        ui.small("All moves and arrangements are one validated Undo step. Curves are retained, not flattened.");
    }
}
