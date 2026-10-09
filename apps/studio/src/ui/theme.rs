//! Consistent high-contrast desktop styling for the native design workspace.
use eframe::egui::{self, Color32};

pub(crate) fn install(ctx:&egui::Context) {
    ctx.set_theme(egui::Theme::Dark);
    let mut style=(*ctx.style_of(egui::Theme::Dark)).clone();
    style.visuals=egui::Visuals::dark();
    style.visuals.window_fill=Color32::from_rgb(27,33,42);
    style.visuals.panel_fill=Color32::from_rgb(30,37,48);
    style.visuals.extreme_bg_color=Color32::from_rgb(21,27,36);
    style.visuals.faint_bg_color=Color32::from_rgb(39,49,61);
    style.visuals.widgets.inactive.bg_fill=Color32::from_rgb(49,63,80);
    style.visuals.widgets.hovered.bg_fill=Color32::from_rgb(65,90,117);
    style.visuals.widgets.active.bg_fill=Color32::from_rgb(54,108,147);
    style.visuals.selection.bg_fill=Color32::from_rgb(47,111,159);
    style.visuals.selection.stroke.color=Color32::WHITE;
    style.text_styles.insert(egui::TextStyle::Body,egui::FontId::proportional(14.0));
    style.text_styles.insert(egui::TextStyle::Button,egui::FontId::proportional(14.0));
    style.text_styles.insert(egui::TextStyle::Small,egui::FontId::proportional(12.0));
    style.text_styles.insert(egui::TextStyle::Heading,egui::FontId::proportional(17.0));
    style.text_styles.insert(egui::TextStyle::Monospace,egui::FontId::monospace(13.0));
    style.spacing.item_spacing=egui::vec2(6.0,6.0);
    style.spacing.button_padding=egui::vec2(10.0,6.0);
    style.spacing.interact_size.y=30.0;
    ctx.set_style_of(egui::Theme::Dark,style);
}

pub(crate) const ACCENT:Color32=Color32::from_rgb(114,186,222);
pub(crate) const MUTED:Color32=Color32::from_rgb(160,174,189);
pub(crate) const CANVAS:Color32=Color32::from_rgb(25,31,39);
pub(crate) const STOCK:Color32=Color32::from_rgb(238,226,205);
pub(crate) const GRID:Color32=Color32::from_rgb(205,196,179);
pub(crate) const VECTOR:Color32=Color32::from_rgb(45,91,130);
pub(crate) const SELECTION:Color32=Color32::from_rgb(249,159,55);
