//! Native, bounded SVG path interchange. Curves remain analytic CAD sources.
//! Unsupported geometry and transformations reject the entire import.
use crate::{AnalyticPath,Curve,PathNode,PathSegment,Point,Project,MAX_COORD_MM};
use std::f64::consts::{PI,TAU};
use svgtypes::{PathParser,PathSegment as Segment};
const SVG_NS:&str="http://www.w3.org/2000/svg";
const LIMIT:usize=16*1024*1024;
#[derive(Debug)]
pub struct SvgVectors{
    pub paths:Vec<AnalyticPath>,
    pub width_mm:f64,
    pub height_mm:f64,
}
fn mm(s:&str)->Result<f64,String>{
    let number=s.trim().strip_suffix("mm").unwrap_or(s.trim());
    let n=number.parse::<f64>().map_err(|_|format!("Invalid SVG dimension {s}: expected mm"))?;
    if !(0.001..=MAX_COORD_MM).contains(&n){return Err("SVG dimensions outside safe mm range".into());}
    Ok(n)
}
fn flip(p:Point,h:f64)->Point{Point::new(p.x,h-p.y)}
fn dist(a:Point,b:Point)->f64{(a.x-b.x).hypot(a.y-b.y)}
fn center(a:Point,b:Point,r:f64,large:bool,sweep:bool)->Result<Point,String>{
    let dx=b.x-a.x;let dy=b.y-a.y;let chord=dx.hypot(dy);
    if !r.is_finite()||r<=0.0||chord<1e-8||chord>2.0*r+1e-7{
        return Err("SVG circular arc radius/chord is invalid".into());
    }
    let mid=Point::new((a.x+b.x)*0.5,(a.y+b.y)*0.5);
    let altitude=(r*r-(chord*0.5).powi(2)).max(0.0).sqrt();
    for sign in [1.0,-1.0]{
        let c=Point::new(mid.x-sign*dy*altitude/chord,
            mid.y+sign*dx*altitude/chord);
        let aa=(a.y-c.y).atan2(a.x-c.x);
        let bb=(b.y-c.y).atan2(b.x-c.x);
        let angle=if sweep{(bb-aa).rem_euclid(TAU)}
            else{(aa-bb).rem_euclid(TAU)};
        if (angle>PI+1e-8)==large||(angle-PI).abs()<1e-8{return Ok(c);}
    }
    Err("Cannot retain the SVG circular arc sweep".into())
}
fn one(d:&str,name:String,h:f64,visible:bool,locked:bool)->Result<AnalyticPath,String>{
    let mut first=None;
    let mut here=Point::new(0.0,0.0);
    let mut edges:Vec<(Point,Curve)>=Vec::new();
    let mut closed=false;
    for command in PathParser::from(d){
        let command=command.map_err(|e|format!("Invalid SVG path data: {e}"))?;
        if edges.len()>=256{return Err("SVG has too many path edges".into());}
        let pos=|x:f64,y:f64,abs:bool|{
            if abs{Point::new(x,y)}else{Point::new(here.x+x,here.y+y)}
        };
        let (end,curve)=match command{
            Segment::MoveTo{abs,x,y}=>{
                if first.is_some(){return Err("SVG multiple subpaths: separate them into paths".into());}
                here=pos(x,y,abs);
                first=Some(here);
                continue;
            }
            Segment::LineTo{abs,x,y}=>(pos(x,y,abs),Curve::Line),
            Segment::HorizontalLineTo{abs,x}=>
                (Point::new(if abs{x}else{here.x+x},here.y),Curve::Line),
            Segment::VerticalLineTo{abs,y}=>
                (Point::new(here.x,if abs{y}else{here.y+y}),Curve::Line),
            Segment::CurveTo{abs,x1,y1,x2,y2,x,y}=>(
                pos(x,y,abs),Curve::Cubic{
                    control1:pos(x1,y1,abs),control2:pos(x2,y2,abs)
                }),
            Segment::EllipticalArc{abs,rx,ry,x_axis_rotation,large_arc,sweep,x,y}=>{
                if (rx-ry).abs()>1e-8*rx.abs().max(ry.abs()).max(1.0)
                    || x_axis_rotation.abs()>1e-8{
                    return Err("SVG elliptical/rotated arcs not supported; use circular A arcs".into());
                }
                let end=pos(x,y,abs);
                (end,Curve::Arc{center:center(here,end,rx,large_arc,sweep)?,
                    clockwise:sweep})
            }
            Segment::ClosePath{..}=>{
                if closed{return Err("Repeated SVG path close".into());}
                let start=first.ok_or("SVG path closes without M")?;
                if dist(here,start)>1e-8{edges.push((start,Curve::Line));}
                here=start;closed=true;continue;
            }
            _=>return Err("Unsupported SVG path command; use M/L/H/V/C/A/Z".into()),
        };
        if first.is_none(){return Err("SVG path must start with M".into());}
        if closed{return Err("SVG segments after Z are unsupported".into());}
        if !end.finite(){return Err("Nonfinite SVG endpoint".into());}
        edges.push((end,curve));
        here=end;
    }
    let first=first.ok_or("SVG path missing M")?;
    if edges.is_empty(){return Err("SVG path has no segments".into());}
    let mut points=vec![first];
    for (i,(p,_)) in edges.iter().enumerate(){
        if !closed||i+1<edges.len(){points.push(*p);}
    }
    let n=points.len() as u64;
    let nodes=points.into_iter().enumerate().map(|(i,p)|PathNode{
        id:i as u64+1,position:flip(p,h)
    }).collect();
    let count=edges.len();
    let segments=edges.into_iter().enumerate().map(|(i,(_,c))|{
        let curve=match c{
            Curve::Line=>Curve::Line,
            Curve::Arc{center,clockwise}=>Curve::Arc{center:flip(center,h),clockwise},
            Curve::Cubic{control1,control2}=>Curve::Cubic{
                control1:flip(control1,h),control2:flip(control2,h)
            },
        };
        PathSegment{id:n+i as u64+1,curve}
    }).collect();
    let path=AnalyticPath{id:1,name,origin:Point::new(0.0,0.0),
        visible,locked,closed,nodes,segments,next_element_id:n+count as u64+1};
    path.validate()?;
    Ok(path)
}
fn bool_attr(v:Option<&str>,default:bool)->Result<bool,String>{
    match v{None=>Ok(default),Some("true")=>Ok(true),Some("false")=>Ok(false),
        _=>Err("Invalid SVG vector visibility/lock metadata".into())}
}
fn children(node:roxmltree::Node<'_,'_>,h:f64,out:&mut Vec<AnalyticPath>)->Result<(),String>{
    for child in node.children().filter(|x|x.is_element()){
        if child.tag_name().namespace().is_some_and(|ns|ns!=SVG_NS){continue;}
        let kind=child.tag_name().name();
        if child.attribute("transform").is_some(){
            return Err("SVG transforms are not supported; bake transforms first".into());
        }
        match kind{
            "g"=>children(child,h,out)?,
            "path"=>{
                if out.len()>=512{return Err("SVG exceeds 512 vectors".into());}
                let d=child.attribute("d").ok_or("SVG path lacks d")?;
                let name=child.attribute("data-cf-name").or_else(||child.attribute("id"))
                    .filter(|s|!s.is_empty()).unwrap_or("Imported vector");
                out.push(one(d,name.to_owned(),h,
                    bool_attr(child.attribute("data-cf-visible"),true)?,
                    bool_attr(child.attribute("data-cf-locked"),false)?)?);
            }
            "title"|"desc"|"metadata"=>{}
            _=>return Err(format!("SVG <{kind}> is not supported; convert to a path first")),
        }
    }
    Ok(())
}
pub fn import_svg(input:&[u8])->Result<SvgVectors,String>{
    if input.len()>LIMIT{return Err("SVG exceeds 16 MiB".into());}
    let text=std::str::from_utf8(input).map_err(|_|"SVG requires UTF-8")?;
    if text.contains("<!DOCTYPE"){return Err("SVG DTD/DOCTYPE is unsupported".into());}
    let doc=roxmltree::Document::parse(text)
        .map_err(|e|format!("Invalid SVG XML: {e}"))?;
    let root=doc.root_element();
    if root.tag_name().name()!="svg"{return Err("Expected SVG root".into());}
    if root.attribute("transform").is_some(){return Err("SVG root transform unsupported".into());}
    let (w,h)=if let Some(view)=root.attribute("viewBox"){
        let v=view.split_whitespace().map(str::parse::<f64>)
            .collect::<Result<Vec<_>,_>>().map_err(|_|"Invalid SVG viewBox")?;
        if v.len()!=4||v[0]!=0.0||v[1]!=0.0{
            return Err("SVG viewBox must start at 0 0 and have four numbers".into());
        }
        (v[2],v[3])
    }else{
        (mm(root.attribute("width").ok_or("SVG width missing")?)?,
         mm(root.attribute("height").ok_or("SVG height missing")?)?)
    };
    if !(0.001..=MAX_COORD_MM).contains(&w)||!(0.001..=MAX_COORD_MM).contains(&h){
        return Err("SVG viewBox dimensions out of bounds".into());
    }
    if let Some(width)=root.attribute("width")
        && (mm(width)?-w).abs()>1e-6{return Err("SVG width differs from viewBox".into());}
    if let Some(height)=root.attribute("height")
        && (mm(height)?-h).abs()>1e-6{return Err("SVG height differs from viewBox".into());}
    let mut paths=Vec::new();
    children(root,h,&mut paths)?;
    if paths.is_empty(){return Err("No SVG paths to import".into());}
    Ok(SvgVectors{paths,width_mm:w,height_mm:h})
}
fn escape(s:&str)->String{
    let mut out=String::new();
    for c in s.chars(){
        match c{
            '&'=>out.push_str("&amp;"),'<'=>out.push_str("&lt;"),
            '>'=>out.push_str("&gt;"),'"'=>out.push_str("&quot;"),
            '\''=>out.push_str("&apos;"),'\n'=>out.push_str("&#10;"),
            '\r'=>out.push_str("&#13;"),'\t'=>out.push_str("&#9;"),
            _=>out.push(c)
        }
    }
    out
}
fn path_data(p:&AnalyticPath,h:f64)->String{
    let start=flip(p.nodes[0].position.offset(p.origin.x,p.origin.y),h);
    let mut d=format!("M {} {}",start.x,start.y);
    for (i,s) in p.segments.iter().enumerate(){
        let end=flip(p.nodes[(i+1)%p.nodes.len()].position
            .offset(p.origin.x,p.origin.y),h);
        match s.curve{
            Curve::Line=>d.push_str(&format!(" L {} {}",end.x,end.y)),
            Curve::Cubic{control1,control2}=>{
                let a=flip(control1.offset(p.origin.x,p.origin.y),h);
                let b=flip(control2.offset(p.origin.x,p.origin.y),h);
                d.push_str(&format!(" C {} {} {} {} {} {}",a.x,a.y,b.x,b.y,end.x,end.y));
            }
            Curve::Arc{center,clockwise}=>{
                let a=p.nodes[i].position;
                let b=p.nodes[(i+1)%p.nodes.len()].position;
                let r=dist(a,center);
                let aa=(a.y-center.y).atan2(a.x-center.x);
                let bb=(b.y-center.y).atan2(b.x-center.x);
                let sweep=if clockwise{(aa-bb).rem_euclid(TAU)}
                    else{(bb-aa).rem_euclid(TAU)};
                d.push_str(&format!(" A {r} {r} 0 {} {} {} {}",
                    u8::from(sweep>PI),u8::from(clockwise),end.x,end.y));
            }
        }
    }
    if p.closed{d.push_str(" Z");}
    d
}
pub fn export_svg(project:&Project)->Result<String,String>{
    project.validate()?;
    let w=project.stock.width_mm;let h=project.stock.height_mm;
    let mut svg=format!("<svg xmlns=\"{SVG_NS}\" width=\"{w}mm\" height=\"{h}mm\" viewBox=\"0 0 {w} {h}\">\n");
    for p in &project.paths{
        svg.push_str(&format!("  <path id=\"vector-{}\" data-cf-name=\"{}\" data-cf-visible=\"{}\" data-cf-locked=\"{}\" d=\"{}\" fill=\"none\" stroke=\"black\"/>\n",
            p.id,escape(&p.name),p.visible,p.locked,path_data(p,h)));
    }
    for p in &project.contours{
        let pts=p.world_points();
        let start=flip(pts[0],h);
        let mut d=format!("M {} {}",start.x,start.y);
        for point in pts.into_iter().skip(1){
            let point=flip(point,h);
            d.push_str(&format!(" L {} {}",point.x,point.y));
        }
        d.push_str(" Z");
        svg.push_str(&format!("  <path id=\"contour-{}\" data-cf-name=\"{}\" data-cf-visible=\"{}\" data-cf-locked=\"{}\" d=\"{}\" fill=\"none\" stroke=\"black\"/>\n",
            p.id,escape(&p.name),p.visible,p.locked,d));
    }
    svg.push_str("</svg>\n");
    if svg.len()>LIMIT{return Err("SVG export exceeds 16 MiB".into());}
    Ok(svg)
}
#[cfg(test)]
mod tests{
    use super::*;
    use crate::{Action,Editor,Primitive};
    #[test]
    fn retains_lines_circles_and_cubic_data(){
        let mut editor=Editor::default();
        for (i,kind) in [Primitive::Line,Primitive::Arc,Primitive::Cubic]
            .into_iter().enumerate(){
            editor.apply(Action::AddAnalytic{
                name:format!("Test & \"{i}\""),
                origin:Point::new(10.0+40.0*i as f64,35.0),
                kind,width_mm:25.0,height_mm:20.0
            }).unwrap();
        }
        let original=&editor.project;
        let text=export_svg(original).unwrap();
        let imported=import_svg(text.as_bytes()).unwrap();
        assert_eq!(imported.paths.len(),3);
        for (a,b) in original.paths.iter().zip(imported.paths.iter()){
            assert_eq!(a.name,b.name);
            assert_eq!(a.nodes.len(),b.nodes.len());
            for (a_node,b_node) in a.nodes.iter().zip(b.nodes.iter()){
                let orig=a_node.position.offset(a.origin.x,a.origin.y);
                assert!(dist(orig,b_node.position)<1e-7);
            }
            assert_eq!(std::mem::discriminant(&a.segments[0].curve),
                std::mem::discriminant(&b.segments[0].curve));
            b.validate().unwrap();
        }
    }
    #[test]
    fn closes_relative_paths(){
        let xml=br#"<svg width="100mm" height="70mm"><path d="M 10 10 l 20 0 v 20 h -20 z"/></svg>"#;
        let out=import_svg(xml).unwrap();
        assert!(out.paths[0].closed);
        assert_eq!(out.paths[0].nodes.len(),4);
        assert_eq!(out.paths[0].segments.len(),4);
    }
    #[test]
    fn rejects_unsupported_unsafe_and_unrepresentable_paths(){
        for xml in [
            r#"<svg width="100mm" height="70mm"><rect width="5" height="4"/></svg>"#,
            r#"<svg width="100mm" height="70mm"><path d="M 0 0 Q 3 3 8 8"/></svg>"#,
            r#"<svg width="100mm" height="70mm"><path transform="scale(2)" d="M 0 0 L 5 5"/></svg>"#,
            r#"<svg width="100mm" height="70mm"><path d="M 0 0 A 10 20 0 0 1 20 0"/></svg>"#,
            r#"<svg width="100mm" height="70mm"><path d="M 0 0 L 5 5 M 8 8 L 9 9"/></svg>"#,
        ]{assert!(import_svg(xml.as_bytes()).is_err(),"{xml}");}
    }
}
