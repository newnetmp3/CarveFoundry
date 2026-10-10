//! Retained system-font text with exact quadratic -> cubic outline conversion.
//! Font binaries are never embedded in designs; geometries remain portable.
use serde::{Deserialize,Serialize};
use ttf_parser::{Face,OutlineBuilder};
use crate::{AnalyticPath,Curve,PathNode,PathSegment,Point};
use std::collections::HashSet;

#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TextSpec {
    pub text:String,
    pub family:String,
    pub postscript:String,
    pub height_mm:f64,
    pub tracking_mm:f64,
    pub origin:Point,
}
impl TextSpec {
    pub fn validate(&self)->Result<(),String>{
        if self.text.is_empty() || self.text.chars().count()>96
            || self.text.chars().any(|c|c.is_control())
            || self.family.is_empty() || self.family.len()>128
            || self.postscript.is_empty() || self.postscript.len()>128
            || !self.origin.finite()
            || !self.height_mm.is_finite() || !(0.5..=1000.0).contains(&self.height_mm)
            || !self.tracking_mm.is_finite() || !(-50.0..=100.0).contains(&self.tracking_mm){
            return Err("Text needs 1–96 single-line characters, font, valid origin, height and tracking".into());
        }
        Ok(())
    }
}
#[derive(Clone,Debug,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TextRun{
    pub id:u64,
    pub spec:TextSpec,
    pub outline_ids:Vec<u64>,
}
impl TextRun{
    pub fn validate(&self)->Result<(),String>{
        self.spec.validate()?;
        if self.id==0 || self.outline_ids.is_empty()
            || self.outline_ids.len()>512
            || self.outline_ids.contains(&0)
            || self.outline_ids.iter().copied().collect::<HashSet<_>>().len()!=self.outline_ids.len(){
            return Err("Text source must reference distinct editable outlines".into());
        }
        Ok(())
    }
}
#[derive(Default)]
struct Contour{
    points:Vec<Point>,
    curves:Vec<Curve>,
    closed:bool,
}
struct GeometryBuilder{
    x:f64,
    y:f64,
    scale:f64,
    origin:Point,
    current:Contour,
    ready:Vec<Contour>,
    error:Option<String>,
}
impl GeometryBuilder{
    fn xy(&self,x:f32,y:f32)->Point{
        Point::new(self.origin.x+self.x+f64::from(x)*self.scale,
            self.origin.y+self.y+f64::from(y)*self.scale)
    }
    fn push(&mut self,p:Point,c:Curve){
        if self.current.points.is_empty(){
            self.error=Some("Glyph edge before contour start".into());
        } else if self.current.points.len()>=256{
            self.error=Some("Glyph contour exceeds 256 analytic nodes".into());
        } else {
            self.current.curves.push(c);
            self.current.points.push(p);
        }
    }
    fn end(&mut self){
        if self.current.points.is_empty(){return;}
        if self.current.points.len()>1{
            let first=self.current.points[0];
            let last=*self.current.points.last().unwrap_or(&first);
            if (last.x-first.x).hypot(last.y-first.y)<1e-6{
                self.current.points.pop();
            }else{
                self.current.curves.push(Curve::Line);
            }
            self.current.closed=true;
            self.ready.push(std::mem::take(&mut self.current));
        }else{
            self.error=Some("Degenerate one-point font contour".into());
            self.current=Contour::default();
        }
    }
    fn finish(mut self)->Result<Vec<Contour>,String>{
        self.end();
        if let Some(e)=self.error{return Err(e);}
        Ok(self.ready)
    }
}
impl OutlineBuilder for GeometryBuilder {
    fn move_to(&mut self,x:f32,y:f32){
        self.end();
        let p=self.xy(x,y);
        self.current.points.push(p);
    }
    fn line_to(&mut self,x:f32,y:f32){
        self.push(self.xy(x,y),Curve::Line);
    }
    fn quad_to(&mut self,x1:f32,y1:f32,x:f32,y:f32){
        let a=match self.current.points.last(){Some(p)=>*p,None=>{self.error=Some("Quadratic without start".into());return;}};
        let q=self.xy(x1,y1);
        let b=self.xy(x,y);
        // Exact degree elevation: Q(a,q,b) == C(a,a+2/3(q-a),b+2/3(q-b),b)
        self.push(b,Curve::Cubic{
            control1:Point::new(a.x+(q.x-a.x)*2.0/3.0,a.y+(q.y-a.y)*2.0/3.0),
            control2:Point::new(b.x+(q.x-b.x)*2.0/3.0,b.y+(q.y-b.y)*2.0/3.0),
        });
    }
    fn curve_to(&mut self,x1:f32,y1:f32,x2:f32,y2:f32,x:f32,y:f32){
        self.push(self.xy(x,y),Curve::Cubic{
            control1:self.xy(x1,y1),control2:self.xy(x2,y2),
        });
    }
    fn close(&mut self){self.end();}
}
fn convert(contour:Contour,name:String)->Result<AnalyticPath,String>{
    let n=contour.points.len();
    if !(3..=256).contains(&n) || !contour.closed || contour.curves.len()!=n{
        return Err("Font contains an unrepresentable or degenerate outline".into());
    }
    let nodes=contour.points.into_iter().enumerate().map(|(i,p)|
        PathNode{id:i as u64+1,position:p}).collect::<Vec<_>>();
    let segments=contour.curves.into_iter().enumerate().map(|(i,c)|
        PathSegment{id:n as u64+i as u64+1,curve:c}).collect::<Vec<_>>();
    let path=AnalyticPath{id:1,name,origin:Point::new(0.0,0.0),
        visible:true,locked:false,closed:true,nodes,segments,
        next_element_id:(n*2+1) as u64};
    path.validate()?;
    Ok(path)
}
/// Font face bytes are caller-provided from the OS font database.
/// Each font contour stays an editable native analytic path, never a raster.
pub fn outline_text(font_bytes:&[u8],font_index:u32,spec:&TextSpec)
    ->Result<Vec<AnalyticPath>,String>{
    spec.validate()?;
    if font_bytes.len()>32*1024*1024{
        return Err("Font exceeds the 32 MiB parsing limit".into());
    }
    let face=Face::parse(font_bytes,font_index)
        .map_err(|_|"Selected font file is invalid")?;
    if !face.is_outline_embedding_allowed(){
        return Err("Font licensing prohibits outline embedding".into());
    }
    let scale=spec.height_mm/f64::from(face.units_per_em());
    let mut cursor=0.0;
    let mut result=Vec::new();
    for (idx,ch) in spec.text.chars().enumerate(){
        let glyph=face.glyph_index(ch)
            .ok_or_else(||format!("Font does not contain character U+{:04X}",ch as u32))?;
        let advance=face.glyph_hor_advance(glyph)
            .ok_or("Font lacks horizontal glyph advance")?;
        let builder=GeometryBuilder{
            x:cursor,y:0.0,scale,origin:spec.origin,
            current:Contour::default(),ready:Vec::new(),error:None,
        };
        let mut builder=builder;
        if face.outline_glyph(glyph,&mut builder).is_some(){
            for (j,contour) in builder.finish()?.into_iter().enumerate(){
                if result.len()>=512{return Err("Text exceeds 512 outline contours".into());}
                result.push(convert(contour,
                    format!("{} · {}.{}",spec.text.chars().take(22).collect::<String>(),idx+1,j+1))?);
            }
        } else if !ch.is_whitespace(){
            return Err(format!("Glyph U+{:04X} has no vector outline",ch as u32));
        }
        cursor+=f64::from(advance)*scale+spec.tracking_mm;
        if !cursor.is_finite() || cursor.abs()>100_000.0 {
            return Err("Text advances outside the bounded stock coordinate range".into());
        }
    }
    if result.is_empty(){return Err("Text contains no drawable outlines".into());}
    Ok(result)
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn source_requires_finite_settings_and_nonempty_characters(){
        let base=TextSpec{text:"Hello".into(),family:"Example".into(),
            postscript:"Example-Regular".into(),height_mm:20.0,
            tracking_mm:1.0,origin:Point::new(10.0,10.0)};
        base.validate().unwrap();
        let mut bad=base.clone();bad.text="\n".into();assert!(bad.validate().is_err());
        bad=base.clone();bad.height_mm=f64::NAN;assert!(bad.validate().is_err());
        bad=base.clone();bad.text=" ".into();assert!(outline_text(&[],0,&bad).is_err());
    }
    #[test]
    fn quadratics_elevate_exactly_to_cubic(){
        let mut b=GeometryBuilder{x:0.0,y:0.0,scale:1.0,origin:Point::new(0.0,0.0),
            current:Contour::default(),ready:Vec::new(),error:None};
        b.move_to(0.0,0.0);b.quad_to(4.0,6.0,8.0,0.0);
        b.line_to(9.0,-2.0);b.line_to(0.0,0.0);b.close();
        let p=convert(b.finish().unwrap().remove(0),"Curve".into()).unwrap();
        let Curve::Cubic{control1,control2}=p.segments[0].curve else{panic!("not a cubic");};
        assert!((control1.x-8.0/3.0).abs()<1e-10);
        assert!((control1.y-4.0).abs()<1e-10);
        assert!((control2.x-16.0/3.0).abs()<1e-10);
        assert!((control2.y-4.0).abs()<1e-10);
    }
}
