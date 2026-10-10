//! System-font typography dialog: retained text source + editable native outlines.
use super::super::Studio;
use carvefoundry_core::{Action,Point,TextSpec};
use eframe::egui;

#[derive(Clone,Debug)]
pub(crate) struct FaceChoice{
    pub(crate) family:String,
    pub(crate) postscript:String,
    pub(crate) style:String,
}
impl Studio{
    pub(crate) fn start_text(&mut self){
        self.text_edit_id=None;
        self.text_spec=TextSpec{
            text:"US NAVY".into(),family:String::new(),postscript:String::new(),
            height_mm:24.0,tracking_mm:0.0,origin:Point::new(20.0,80.0),
        };
        if let Some(choice)=self.font_choices.iter().find(|f|
            f.family=="DejaVu Sans" && f.style=="Normal")
            .or_else(||self.font_choices.iter().find(|f|f.style=="Normal"))
            .or_else(||self.font_choices.first()){
            self.text_spec.family=choice.family.clone();
            self.text_spec.postscript=choice.postscript.clone();
        }
        self.text_error.clear();
        self.text_dialog=true;
    }
    pub(crate) fn edit_text_for_path(&mut self,id:u64){
        if let Some(run)=self.editor.project.text_runs.iter()
            .find(|run|run.outline_ids.contains(&id)).cloned(){
            self.text_spec=run.spec;
            self.text_edit_id=Some(run.id);
            self.text_error.clear();
            self.text_dialog=true;
        }
    }
    fn commit_text(&mut self)->Result<usize,String>{
        let face_id=self.font_database.faces().find(|f|
            f.post_script_name==self.text_spec.postscript
            && f.families.iter().any(|(name,_)|name==&self.text_spec.family))
            .map(|f|f.id).ok_or("Selected system font is not installed. Existing vector outlines remain usable.")?;
        let generated=self.font_database.with_face_data(face_id,|data,index|
            carvefoundry_core::outline_text(data,index,&self.text_spec))
            .ok_or("Cannot read selected system font")??;
        let count=generated.len();
        self.editor.apply(Action::SetText{
            id:self.text_edit_id,spec:self.text_spec.clone(),paths:generated,
        })?;
        let last=self.editor.project.text_runs.last()
            .ok_or("Text source commit failed")?;
        let ids=last.outline_ids.clone();
        self.selected_ids=ids.into_iter().collect();
        self.selected_path=None;self.selected=None;self.selected_node=None;
        self.selected_handle=None;
        self.reconcile_selection();
        self.status=format!("Generated {count} exact font outlines. Text source stays editable in .cfd.");
        self.text_dialog=false;
        Ok(count)
    }
    pub(crate) fn text_overlay(&mut self,ctx:&egui::Context){
        if !self.text_dialog{return;}
        let mut open=true;
        let mut commit=false;
        egui::Window::new(if self.text_edit_id.is_some(){"Edit vector text"}else{"Create vector text"})
            .open(&mut open).resizable(true).default_width(435.0)
            .show(ctx,|ui|{
                ui.label("Text (single line, up to 96 characters)");
                ui.add(egui::TextEdit::singleline(&mut self.text_spec.text)
                    .desired_width(f32::INFINITY));
                ui.separator();
                let mut family=self.text_spec.family.clone();
                let families=self.font_choices.iter()
                    .map(|f|f.family.clone())
                    .collect::<std::collections::BTreeSet<_>>();
                ui.label("Installed font family");
                egui::ComboBox::from_id_salt("font-family")
                    .selected_text(if family.is_empty(){"No fonts found"}else{&family})
                    .width(330.0).show_ui(ui,|ui|{
                        egui::ScrollArea::vertical().max_height(220.0).show(ui,|ui|{
                            for f in &families{ui.selectable_value(&mut family,f.clone(),f);}
                        });
                    });
                if family!=self.text_spec.family{
                    self.text_spec.family=family.clone();
                    if let Some(f)=self.font_choices.iter()
                        .find(|f|f.family==family && f.style=="Normal")
                        .or_else(||self.font_choices.iter().find(|f|f.family==family)){
                        self.text_spec.postscript=f.postscript.clone();
                    }
                }
                let faces=self.font_choices.iter().filter(|f|f.family==family)
                    .collect::<Vec<_>>();
                ui.label("Typeface / variant");
                egui::ComboBox::from_id_salt("font-variant")
                    .selected_text(faces.iter().find(|f|f.postscript==self.text_spec.postscript)
                        .map_or("Select variant",|f|f.style.as_str()))
                    .width(330.0).show_ui(ui,|ui|{
                        for face in faces {
                            ui.selectable_value(&mut self.text_spec.postscript,
                                face.postscript.clone(),format!("{} ({})",face.style,face.postscript));
                        }
                    });
                ui.separator();
                ui.horizontal(|ui|{
                    ui.label("Em height");
                    ui.add(egui::DragValue::new(&mut self.text_spec.height_mm)
                        .range(0.5..=1000.0).speed(0.5).suffix(" mm"));
                    ui.label("Spacing");
                    ui.add(egui::DragValue::new(&mut self.text_spec.tracking_mm)
                        .range(-50.0..=100.0).speed(0.1).suffix(" mm"));
                });
                ui.horizontal(|ui|{
                    ui.label("X");
                    ui.add(egui::DragValue::new(&mut self.text_spec.origin.x)
                        .speed(0.25).suffix(" mm"));
                    ui.label("Baseline Y");
                    ui.add(egui::DragValue::new(&mut self.text_spec.origin.y)
                        .speed(0.25).suffix(" mm"));
                });
                ui.small("Each glyph contour becomes a native editable line/cubic path. Font outline curves stay exact.");
                ui.small("The .cfd saves text settings and outlines; editing on another computer requires the same installed typeface.");
                if !self.text_error.is_empty(){
                    ui.colored_label(egui::Color32::LIGHT_RED,&self.text_error);
                }
                ui.separator();
                ui.horizontal(|ui|{
                    if ui.button(if self.text_edit_id.is_some(){"Update text"}else{"Create text"})
                        .clicked(){commit=true;}
                    if ui.button("Cancel").clicked(){self.text_dialog=false;}
                });
            });
        if !open{self.text_dialog=false;}
        if commit {
            if let Err(e)=self.commit_text(){self.text_error=e; }
        }
    }
}
