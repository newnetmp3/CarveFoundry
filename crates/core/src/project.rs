//! Stable, versioned Rust project data. Not compatible with historic CF3D.
//!
//! Project files contain design intent, not machine-executable instructions.
use std::{collections::HashSet, fs::{self, OpenOptions}, io::Write, path::Path};
use serde::{Deserialize, Serialize};
use crate::geometry::{Point, validate_polygon};
use crate::path::AnalyticPath;

pub const MAX_COORD_MM: f64 = 100_000.0;
pub const PROJECT_VERSION: u32 = 1;
pub const MAX_PROJECT_BYTES: u64 = 16 * 1024 * 1024;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Stock {
    pub width_mm: f64,
    pub height_mm: f64,
    pub thickness_mm: f64,
}
impl Default for Stock {
    fn default() -> Self { Self { width_mm:300., height_mm:200., thickness_mm:19. } }
}
impl Stock {
    pub fn validate(&self) -> Result<(), String> {
        if [self.width_mm,self.height_mm,self.thickness_mm].iter()
            .any(|v| !v.is_finite() || *v<=0. || *v>MAX_COORD_MM) {
            return Err("Stock dimensions must be finite, positive and within 100,000 mm".into());
        }
        Ok(())
    }
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Fixture {
    pub name: String,
    pub min: Point,
    pub max: Point,
    /// Z of fence top relative to the stock's top face (the job Z0).
    pub top_z_mm: f64,
    pub clearance_mm: f64,
}
impl Fixture {
    pub fn validate(&self) -> Result<(), String> {
        if self.name.trim().is_empty() || self.name.len()>128
            || !self.min.finite() || !self.max.finite()
            || self.min.x >= self.max.x || self.min.y >= self.max.y
            || !self.top_z_mm.is_finite() || self.top_z_mm.abs()>MAX_COORD_MM
            || !self.clearance_mm.is_finite()
            || !(0.0..=MAX_COORD_MM).contains(&self.clearance_mm) {
            return Err("Invalid stock-relative fixture keep-out".into());
        }
        Ok(())
    }
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Contour {
    pub id: u64,
    pub name: String,
    pub visible: bool,
    pub locked: bool,
    pub origin: Point,
    pub vertices: Vec<Point>,
}
impl Contour {
    pub fn world_points(&self) -> Vec<Point> {
        self.vertices.iter().map(|p| p.offset(self.origin.x,self.origin.y)).collect()
    }
    pub fn validate(&self) -> Result<(), String> {
        if self.id==0 || self.name.trim().is_empty() || self.name.len()>256
            || !self.origin.finite() {
            return Err("Invalid contour identity, name, or translation".into());
        }
        validate_polygon(&self.vertices)?;
        if self.world_points().iter().any(|p| !p.finite()) {
            return Err("Contour extends beyond finite design bounds".into());
        }
        Ok(())
    }
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Project {
    pub schema_version: u32,
    pub name: String,
    pub stock: Stock,
    pub contours: Vec<Contour>,
    /// Analytic paths coexist with R0 polygon contours without changing their saved schema.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub paths: Vec<AnalyticPath>,
    pub fixtures: Vec<Fixture>,
    /// Editable text source descriptors; glyph outlines are ordinary native paths.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub text_runs: Vec<crate::text::TextRun>,
    /// Optional organization metadata; absent in pre-R1e native designs.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub layers:Vec<crate::organization::DesignLayer>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub layer_members:Vec<crate::organization::LayerMember>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub groups:Vec<crate::organization::VectorGroup>,
    pub next_id: u64,
}
impl Default for Project {
    fn default() -> Self {
        Self { schema_version:PROJECT_VERSION, name:"Untitled CNC design".into(),
            stock:Stock::default(), contours:vec![], paths:vec![], fixtures:vec![], text_runs:vec![], layers:vec![],layer_members:vec![],groups:vec![],next_id:1 }
    }
}
impl Project {
    pub fn validate(&self) -> Result<(), String> {
        if self.schema_version!=PROJECT_VERSION {return Err("Unknown project schema version".into());}
        if self.name.trim().is_empty() || self.name.len()>256 {
            return Err("Project name must be 1–256 characters".into());
        }
        self.stock.validate()?;
        if self.contours.len()+self.paths.len()>512 || self.fixtures.len()>1024 {
            return Err("Project exceeds contour or fixture limits".into());
        }
        let mut seen=HashSet::new();
        for contour in &self.contours {
            contour.validate()?;
            if !seen.insert(contour.id) || contour.id>=self.next_id {
                return Err("Duplicate or unstable contour identifiers".into());
            }
        }
        for path in &self.paths {
            path.validate()?;
            if !seen.insert(path.id) || path.id>=self.next_id {
                return Err("Duplicate or unstable analytic path identity".into());
            }
        }
        if self.text_runs.len()>512{return Err("Too many editable text sources".into());}
        let mut referenced=HashSet::new();
        for label in &self.text_runs{
            label.validate()?;
            if label.id>=self.next_id||!seen.insert(label.id){
                return Err("Duplicate text source ID".into());
            }
            for id in &label.outline_ids{
                if !referenced.insert(*id)||!self.paths.iter().any(|p|p.id==*id){
                    return Err("Text source references missing/duplicate outline".into());
                }
            }
        }
        self.validate_organization()?;
        for fixture in &self.fixtures { fixture.validate()?; }
        Ok(())
    }
    /// Visual setup warnings only: no CAM, collision prediction or NC output.
    pub fn design_warnings(&self) -> Vec<String> {
        let mut result=vec![];
        for part in &self.contours {
            if part.world_points().iter().any(|p|
                p.x<0. || p.y<0. || p.x>self.stock.width_mm
                    || p.y>self.stock.height_mm) {
                result.push(format!("{} extends outside configured stock",part.name));
            }
        }
        for path in &self.paths {
            // Visualization-only: does not check cutter radius or holder clearance.
            if let Ok(points)=path.preview_points(0.25)
                && points.iter().any(|p| p.x<0.0 || p.y<0.0
                    || p.x>self.stock.width_mm || p.y>self.stock.height_mm) {
                    result.push(format!("{} extends outside configured stock",path.name));
                }
        }
        if !self.fixtures.is_empty() {
            result.push(format!("{} fixture(s) recorded; machine clearance NOT verified",
                self.fixtures.len()));
        }
        result
    }
    pub fn decode(data: &[u8]) -> Result<Self, String> {
        if data.len() as u64>MAX_PROJECT_BYTES {
            return Err("Project exceeds 16 MiB safety bound".into());
        }
        let project: Self=serde_json::from_slice(data)
            .map_err(|e|format!("Invalid Rust project JSON: {e}"))?;
        project.validate()?;
        Ok(project)
    }
    pub fn encode(&self) -> Result<Vec<u8>, String> {
        self.validate()?;
        let bytes=serde_json::to_vec_pretty(self).map_err(|e|e.to_string())?;
        if bytes.len() as u64>MAX_PROJECT_BYTES {
            return Err("Serialized project exceeds 16 MiB".into());
        }
        Ok(bytes)
    }
    pub fn open(path: &Path) -> Result<Self, String> {
        let meta=fs::metadata(path).map_err(|e|e.to_string())?;
        if meta.len()>MAX_PROJECT_BYTES { return Err("Project file exceeds 16 MiB".into()); }
        let bytes=fs::read(path).map_err(|e|e.to_string())?;
        Self::decode(&bytes)
    }
    pub fn save(&self, path: &Path) -> Result<(), String> {
        let data=self.encode()?;
        if path.extension().and_then(|v|v.to_str())!=Some("cfd") {
            return Err("Rust-native projects must use the .cfd extension".into());
        }
        // Same-directory staging + rename prevents truncating a valid save.
        // The path is explicitly chosen by the user; this is NOT legacy CF3D.
        let name=path.file_name().and_then(|v|v.to_str())
            .ok_or("Project path must contain a valid filename")?;
        let mut scratch=path.to_path_buf();
        scratch.set_file_name(format!(".{name}.{}.part",std::process::id()));
        let mut stream=OpenOptions::new().write(true).create_new(true).open(&scratch)
            .map_err(|e|format!("Could not create staging file: {e}"))?;
        let result=(||->std::io::Result<()> {
            stream.write_all(&data)?;
            stream.sync_all()?;
            fs::rename(&scratch,path)?;
            Ok(())
        })();
        if result.is_err() {let _=fs::remove_file(&scratch);}
        result.map_err(|e|format!("Could not publish project: {e}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn old_r0_project_opens_and_new_analytic_format_roundtrips() {
        use crate::path::{AnalyticPath, Primitive, Curve};
        let legacy=r#"{
            "schema_version":1,"name":"Old layout",
            "stock":{"width_mm":300.0,"height_mm":200.0,"thickness_mm":19.0},
            "contours":[],"fixtures":[],"next_id":1
        }"#;
        let mut p=Project::decode(legacy.as_bytes()).unwrap();
        assert!(p.paths.is_empty());
        p.paths.push(AnalyticPath::preset(1,"Original curve".into(),
            Point::new(20.0,20.0),Primitive::Cubic,70.0,25.0).unwrap());
        p.next_id=2;
        let encoded=p.encode().unwrap();
        let reload=Project::decode(&encoded).unwrap();
        assert_eq!(reload,p);
        assert!(matches!(reload.paths[0].segments[0].curve,Curve::Cubic{..}));
        assert_eq!(reload.paths[0].nodes[0].id,1);
        assert_eq!(reload.paths[0].segments[0].id,3);
    }
    #[test]
    fn ids_must_be_globally_distinct_across_polygon_and_analytic_paths(){
        use crate::path::{AnalyticPath,Primitive};
        let mut p=Project{next_id:2,..Project::default()};
        p.contours.push(Contour{id:1,name:"Rectangle".into(),visible:true,
            locked:false,origin:Point::new(0.0,0.0),
            vertices:vec![Point::new(0.0,0.0),Point::new(10.0,0.0),
                Point::new(0.0,10.0)]});
        p.paths.push(AnalyticPath::preset(1,"Duplicate ID".into(),
            Point::new(0.0,0.0),Primitive::Line,10.0,10.0).unwrap());
        assert!(p.validate().is_err());
    }
    #[test]
    fn strict_project_roundtrip_and_schema_fail_closed() {
        let project=Project::default();
        let bytes=project.encode().unwrap();
        assert_eq!(Project::decode(&bytes).unwrap(),project);
        let mut other=project.clone();
        other.schema_version=2;
        assert!(other.encode().is_err());
        assert!(Project::decode(&vec![b' ';MAX_PROJECT_BYTES as usize+1]).is_err());
    }
    #[test]
    fn stock_and_fence_height_are_in_stock_relative_coordinates() {
        let mut p=Project::default();
        p.fixtures.push(Fixture {name:"Left fence".into(),
            min:Point::new(-5.,0.),max:Point::new(0.,200.),
            top_z_mm:23.-19.,clearance_mm:2.});
        p.validate().unwrap();
        assert_eq!(p.fixtures[0].top_z_mm,4.);
        assert_eq!(p.design_warnings().len(),1);
        p.fixtures[0].clearance_mm=-1.;
        assert!(p.validate().is_err());
    }
    #[test]
    fn rejects_duplicate_identifiers_and_nonfinite_stock() {
        let mut p=Project::default();
        p.stock.width_mm=f64::INFINITY;
        assert!(p.validate().is_err());
        p.stock.width_mm=300.;
        p.contours.push(Contour{id:1,name:"A".into(),visible:true,locked:false,
            origin:Point::new(0.,0.),
            vertices:vec![Point::new(0.,0.),Point::new(3.,0.),Point::new(0.,3.)]});
        p.contours.push(p.contours[0].clone());
        p.next_id=2;
        assert!(p.validate().is_err());
    }
}
