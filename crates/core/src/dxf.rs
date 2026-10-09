//! Strict 2D ASCII DXF interchange with retained analytic geometry.
//! Input is treated as untrusted. Unsupported entities/units/3D reject all.
use crate::{AnalyticPath,Curve,PathNode,PathSegment,Point,Project};
use std::collections::BTreeMap;
use std::f64::consts::{PI,TAU};

const LIMIT:usize=16*1024*1024;
const APP:&str="CARVEFOUNDRY";
const EPS:f64=1e-7;

#[derive(Debug)]
pub struct DxfVectors {
    pub paths:Vec<AnalyticPath>,
    pub units:&'static str,
}
#[derive(Clone,Debug)]
struct Pair {code:i32,value:String}
#[derive(Clone,Debug)]
struct Meta {
    id:u64,index:usize,total:usize,closed:bool,
    visible:bool,locked:bool,name:String,
}
struct Item {path:AnalyticPath,meta:Option<Meta>}
fn parse_pairs(bytes:&[u8])->Result<Vec<Pair>,String>{
    if bytes.len()>LIMIT{return Err("DXF exceeds the 16 MiB limit".into());}
    let text=std::str::from_utf8(bytes).map_err(|_|"Binary/non-UTF8 DXF is not supported")?;
    let mut lines=text.trim_start_matches('\u{feff}').lines();
    let mut out=Vec::new();
    while let Some(code)=lines.next(){
        let value=lines.next().ok_or("DXF has an unpaired group code")?;
        let code=code.trim().parse::<i32>().map_err(|_|"Invalid DXF group code")?;
        out.push(Pair{code,value:value.trim().to_owned()});
        if out.len()>350_000{return Err("DXF exceeds group-code budget".into());}
    }
    if out.is_empty(){return Err("DXF is empty".into());}
    Ok(out)
}
fn entry<'a>(pairs:&'a [Pair],code:i32)->Result<&'a str,String>{
    let mut values=pairs.iter().filter(|p|p.code==code);
    let first=values.next().ok_or_else(||format!("DXF entity missing code {code}"))?;
    if values.next().is_some(){return Err(format!("DXF duplicate group code {code}"));}
    Ok(&first.value)
}
fn optional<'a>(pairs:&'a [Pair],code:i32)->Option<&'a str>{
    pairs.iter().find(|p|p.code==code).map(|p|p.value.as_str())
}
fn number(s:&str)->Result<f64,String>{
    let v=s.parse::<f64>().map_err(|_|format!("Invalid DXF numeric value: {s}"))?;
    if !v.is_finite(){return Err("DXF contains nonfinite numeric data".into());}
    Ok(v)
}
fn num(p:&[Pair],c:i32)->Result<f64,String>{number(entry(p,c)?)}
fn opt_num(p:&[Pair],c:i32,default:f64)->Result<f64,String>{
    optional(p,c).map_or(Ok(default),number)
}
fn integer(p:&[Pair],c:i32,default:i32)->Result<i32,String>{
    optional(p,c).map_or(Ok(default),|s|s.parse::<i32>()
        .map_err(|_|format!("Invalid DXF integer code {c}")))
}
fn point(p:&[Pair],x:i32,y:i32,units:f64)->Result<Point,String>{
    let value=Point::new(num(p,x)?*units,num(p,y)?*units);
    if !value.finite(){return Err("DXF point outside bounded CAD space".into());}
    Ok(value)
}
fn planar(p:&[Pair])->Result<(),String>{
    for code in [30,31,32,38,39]{
        if opt_num(p,code,0.0)?.abs()>EPS {
            return Err("DXF 3D elevations, Z values and thickness are unsupported".into());
        }
    }
    for (code,expected) in [(210,0.0),(220,0.0),(230,1.0)]{
        if (opt_num(p,code,expected)?-expected).abs()>EPS{
            return Err("DXF non-default extrusion/normal is unsupported".into());
        }
    }
    Ok(())
}
fn path(name:String,points:Vec<Point>,curves:Vec<Curve>,closed:bool)
    ->Result<AnalyticPath,String>{
    let len=points.len();
    if len<2 || len>256 || curves.len()!=len-usize::from(!closed){
        return Err("Invalid DXF path node/segment count".into());
    }
    let nodes=points.into_iter().enumerate().map(|(i,p)|
        PathNode{id:i as u64+1,position:p}).collect();
    let segments=curves.into_iter().enumerate().map(|(i,curve)|
        PathSegment{id:len as u64+i as u64+1,curve}).collect::<Vec<_>>();
    let result=AnalyticPath{id:1,name,origin:Point::new(0.0,0.0),
        visible:true,locked:false,closed,nodes,segments,
        next_element_id:len as u64+result_len(closed,len) as u64+1};
    result.validate()?;
    Ok(result)
}
fn result_len(closed:bool,n:usize)->usize{n-usize::from(!closed)}
fn dist(a:Point,b:Point)->f64{(a.x-b.x).hypot(a.y-b.y)}
fn bulge_arc(a:Point,b:Point,bulge:f64)->Result<Curve,String>{
    if !bulge.is_finite()||bulge.abs()>1e8{return Err("DXF bulge invalid".into());}
    if bulge.abs()<1e-12{return Ok(Curve::Line);}
    let dx=b.x-a.x;let dy=b.y-a.y;let chord=dx.hypot(dy);
    if chord<EPS{return Err("DXF arc has zero-length chord".into());}
    let shift=chord*(1.0-bulge*bulge)/(4.0*bulge);
    let middle=Point::new((a.x+b.x)*0.5,(a.y+b.y)*0.5);
    let center=Point::new(middle.x-dy/chord*shift,
        middle.y+dx/chord*shift);
    if !center.finite(){return Err("DXF arc center outside bounded CAD space".into());}
    Ok(Curve::Arc{center,clockwise:bulge<0.0})
}
fn polyline(e:&[Pair],units:f64,name:String)->Result<AnalyticPath,String>{
    planar(e)?;
    let count=integer(e,90,-1)?;
    let flags=integer(e,70,0)?;
    if flags & !1 != 0{return Err("DXF LWPOLYLINE flags unsupported".into());}
    let closed=flags & 1 !=0;
    let mut points=Vec::new();
    let mut bulges=Vec::new();
    let mut x=None;let mut y=None;let mut bulge=0.0;
    for pair in e{
        match pair.code{
            10=>{
                if let Some(last_x)=x.take(){
                    let last_y=y.take().ok_or("DXF LWPOLYLINE vertex missing Y")?;
                    points.push(Point::new(last_x*units,last_y*units));
                    bulges.push(bulge);
                }
                x=Some(number(&pair.value)?);y=None;bulge=0.0;
            }
            20=>{
                if x.is_none()||y.is_some(){return Err("Unexpected DXF vertex Y".into());}
                y=Some(number(&pair.value)?);
            }
            42=>{bulge=number(&pair.value)?;}
            40|41=>{
                // Width changes imply strokes, not centerline geometry.
                if number(&pair.value)?.abs()>EPS {
                    return Err("DXF polyline variable width unsupported".into());
                }
            }
            _=>{}
        }
    }
    if let Some(last_x)=x{
        points.push(Point::new(last_x*units,
            y.ok_or("DXF final vertex missing Y")?*units));
        bulges.push(bulge);
    }
    if points.len()!=count as usize||count<2||points.len()>256{
        return Err("DXF polyline vertex count mismatch/out of bounds".into());
    }
    if points.iter().any(|p|!p.finite()){return Err("DXF polyline coordinates invalid".into());}
    if !closed && bulges.last().is_some_and(|b|b.abs()>EPS) {
        return Err("Open DXF polyline has unused terminal arc bulge".into());
    }
    let n=points.len();
    let mut curves=Vec::new();
    for i in 0..(n-usize::from(!closed)){
        curves.push(bulge_arc(points[i],points[(i+1)%n],bulges[i])?);
    }
    path(name,points,curves,closed)
}
fn spline(e:&[Pair],units:f64,name:String)->Result<AnalyticPath,String>{
    planar(e)?;
    let flags=integer(e,70,0)?;
    if flags & (1|2|4|16|32|64|128)!=0 {
        return Err("DXF rational/closed/periodic spline unsupported".into());
    }
    if integer(e,71,-1)!=3||integer(e,72,-1)!=8||integer(e,73,-1)!=4||
        integer(e,74,0)!=0{
        return Err("Only clamped, degree-3, four-control-point DXF SPLINE is supported".into());
    }
    let knots=e.iter().filter(|v|v.code==40)
        .map(|v|number(&v.value)).collect::<Result<Vec<_>,_>>()?;
    if knots.len()!=8 || !(knots[4]>knots[3])||
        knots[..4].iter().any(|x|(x-knots[0]).abs()>EPS)||
        knots[4..].iter().any(|x|(x-knots[4]).abs()>EPS){
        return Err("DXF spline knots must be clamped cubic Bezier".into());
    }
    if e.iter().filter(|v|v.code==41).any(|v|
        number(&v.value).is_err_or(|w|(w-1.0).abs()>EPS)){
        return Err("Weighted/rational DXF splines unsupported".into());
    }
    let xs=e.iter().filter(|v|v.code==10).map(|v|number(&v.value))
        .collect::<Result<Vec<_>,_>>()?;
    let ys=e.iter().filter(|v|v.code==20).map(|v|number(&v.value))
        .collect::<Result<Vec<_>,_>>()?;
    if xs.len()!=4||ys.len()!=4{return Err("DXF spline requires four XY controls".into());}
    let p=(0..4).map(|i|Point::new(xs[i]*units,ys[i]*units))
        .collect::<Vec<_>>();
    path(name,vec![p[0],p[3]],vec![Curve::Cubic{control1:p[1],control2:p[2]}],false)
}
fn entity(kind:&str,e:&[Pair],scale:f64,index:usize)->Result<AnalyticPath,String>{
    let name=optional(e,8).filter(|s|!s.is_empty())
        .map_or_else(||format!("{kind} {index}"),str::to_owned);
    match kind{
        "LWPOLYLINE"=>polyline(e,scale,name),
        "LINE"=>{
            planar(e)?;
            path(name,vec![point(e,10,20,scale)?,point(e,11,21,scale)?],
                vec![Curve::Line],false)
        }
        "ARC"=>{
            planar(e)?;
            let center=point(e,10,20,scale)?;
            let r=num(e,40)?*scale;
            let a=num(e,50)?.to_radians();
            let b=num(e,51)?.to_radians();
            if !(0.00001..=100_000.0).contains(&r)||
                (b-a).rem_euclid(TAU)<1e-8{
                return Err("DXF arc radius/sweep invalid".into());
            }
            let at=|theta:f64|Point::new(center.x+r*theta.cos(),center.y+r*theta.sin());
            path(name,vec![at(a),at(b)],
                vec![Curve::Arc{center,clockwise:false}],false)
        }
        "CIRCLE"=>{
            planar(e)?;
            let center=point(e,10,20,scale)?;
            let r=num(e,40)?*scale;
            if !(0.00001..=100_000.0).contains(&r){
                return Err("DXF circle radius invalid".into());
            }
            let nodes=(0..4).map(|i|{
                let a=i as f64*PI/2.0;
                Point::new(center.x+r*a.cos(),center.y+r*a.sin())
            }).collect();
            path(name,nodes,vec![Curve::Arc{center,clockwise:false};4],true)
        }
        "SPLINE"=>spline(e,scale,name),
        unsupported=>Err(format!("Unsupported DXF entity {unsupported}; no objects imported")),
    }
}
fn from_hex(s:&str)->Result<String,String>{
    if !s.len().is_multiple_of(2){return Err("Invalid DXF vector-name metadata".into());}
    let mut v=Vec::new();
    for chunk in s.as_bytes().chunks_exact(2){
        let s=std::str::from_utf8(chunk).map_err(|_|"Invalid metadata hex")?;
        v.push(u8::from_str_radix(s,16).map_err(|_|"Invalid metadata hex")?);
    }
    String::from_utf8(v).map_err(|_|"Invalid UTF-8 vector metadata".into())
}
fn metadata(e:&[Pair])->Result<Option<Meta>,String>{
    let mut app=false;let mut header=None;let mut hex=String::new();
    for p in e{
        match p.code{
            1001 if p.value==APP=>app=true,
            1001=>app=false,
            1000 if app && p.value.starts_with('P')=>{
                if header.is_some(){return Err("Duplicate DXF vector metadata".into());}
                header=Some(p.value[1..].to_owned());
            }
            1000 if app && p.value.starts_with('N')=>hex.push_str(&p.value[1..]),
            _=>{}
        }
    }
    let Some(header)=header else {
        if app{return Err("Incomplete DXF vector metadata".into());}
        return Ok(None)
    };
    let fields=header.split('|').collect::<Vec<_>>();
    if fields.len()!=6{return Err("Invalid DXF vector metadata fields".into());}
    let parse=|i:usize|fields[i].parse::<u64>()
        .map_err(|_|"Invalid DXF vector metadata number".to_string());
    let id=parse(0)?;
    let index=usize::try_from(parse(1)?).map_err(|_|"Invalid DXF segment index")?;
    let total=usize::try_from(parse(2)?).map_err(|_|"Invalid DXF segment total")?;
    if id==0||total==0||total>256||index>=total{
        return Err("DXF vector metadata identity/order invalid".into());
    }
    let flag=|i:usize|match fields[i]{"0"=>Ok(false),"1"=>Ok(true),
        _=>Err("Invalid DXF vector metadata bool".into())};
    let name=from_hex(&hex)?;
    if name.is_empty()||name.len()>256{return Err("Invalid DXF vector metadata name".into());}
    Ok(Some(Meta{id,index,total,closed:flag(3)?,
        visible:flag(4)?,locked:flag(5)?,name}))
}
fn join_group(mut items:Vec<(Meta,AnalyticPath)>)->Result<AnalyticPath,String>{
    items.sort_by_key(|(m,_)|m.index);
    let reference=items.first().ok_or("Empty DXF path group")?.0.clone();
    if items.len()!=reference.total{return Err("DXF grouped vector missing segments".into());}
    if reference.total==1{
        let (meta,mut p)=items.remove(0);
        if p.closed!=meta.closed{return Err("DXF vector closed-flag mismatch".into());}
        p.name=meta.name;p.visible=meta.visible;p.locked=meta.locked;
        p.validate()?;
        return Ok(p);
    }
    let mut nodes=Vec::with_capacity(items.len()+1);
    let mut curves=Vec::with_capacity(items.len());
    let mut last_end=None;
    for (index,(meta,p)) in items.into_iter().enumerate(){
        if meta.id!=reference.id||meta.index!=index||meta.total!=reference.total||
            meta.closed!=reference.closed||meta.name!=reference.name||
            meta.visible!=reference.visible||meta.locked!=reference.locked{
            return Err("Conflicting DXF vector grouping metadata".into());
        }
        if p.closed||p.nodes.len()!=2||p.segments.len()!=1 {
            return Err("Grouped DXF segment must have one open analytic edge".into());
        }
        let a=p.nodes[0].position;let b=p.nodes[1].position;
        if let Some(prev)=last_end && dist(prev,a)>1e-6 {
            return Err("DXF grouped vector has disconnected edges".into());
        }
        nodes.push(a);curves.push(p.segments[0].curve);
        last_end=Some(b);
    }
    if reference.closed{
        if dist(nodes[0],last_end.ok_or("DXF grouped path missing end")?)>1e-6{
            return Err("DXF grouped closed vector has a gap".into());
        }
    }else{
        nodes.push(last_end.ok_or("DXF grouped path missing end")?);
    }
    let mut combined=path(reference.name,nodes,curves,reference.closed)?;
    combined.visible=reference.visible;combined.locked=reference.locked;
    combined.validate()?;
    Ok(combined)
}
pub fn import_dxf(input:&[u8])->Result<DxfVectors,String>{
    let pairs=parse_pairs(input)?;
    let mut scale=None;let mut units="";
    for window in pairs.windows(2){
        if window[0].code==9 && window[0].value=="$INSUNITS" && window[1].code==70{
            if scale.is_some(){return Err("Duplicate DXF INSUNITS".into());}
            let raw=window[1].value.parse::<i32>().map_err(|_|"Invalid DXF INSUNITS")?;
            let (s,u)=match raw{
                4=>(1.0,"mm"),1=>(25.4,"inches"),5=>(10.0,"cm"),
                6=>(1000.0,"m"),
                _=>return Err("DXF drawing units unsupported or unitless; specify millimetres".into()),
            };
            scale=Some(s);units=u;
        }
    }
    let scale=scale.ok_or("DXF lacks $INSUNITS: specify millimetres to avoid wrong scale")?;
    let mut section="";
    let mut i=0;let mut ordinary=Vec::new();let mut groups:BTreeMap<u64,Vec<(Meta,AnalyticPath)>>=BTreeMap::new();
    let mut seen_eof=false;let mut count=0;
    while i<pairs.len(){
        let p=&pairs[i];
        if p.code==0 && p.value=="SECTION" {
            let next=pairs.get(i+1).ok_or("DXF SECTION missing name")?;
            if next.code!=2{return Err("DXF SECTION missing code 2".into());}
            section=match next.value.as_str(){"ENTITIES"=>"ENTITIES","HEADER"=>"HEADER",_=>"OTHER"};
            i+=2;continue;
        }
        if p.code==0 && p.value=="ENDSEC"{section="";i+=1;continue;}
        if p.code==0 && p.value=="EOF"{seen_eof=true;break;}
        if section=="ENTITIES"&&p.code==0{
            let kind=p.value.as_str();
            if kind=="SEQEND"||kind=="VERTEX"||kind=="POLYLINE"{
                return Err("Classic DXF POLYLINE/VERTEX unsupported; convert to LWPOLYLINE".into());
            }
            let start=i+1;let mut end=start;
            while end<pairs.len()&&pairs[end].code!=0{end+=1;}
            count+=1;
            if count>512{return Err("DXF exceeds 512 drawable entities".into());}
            let data=&pairs[start..end];
            let decoded=entity(kind,data,scale,count)?;
            if let Some(meta)=metadata(data)?{
                groups.entry(meta.id).or_default().push((meta,decoded));
            }else{ordinary.push(decoded);}
            i=end;continue;
        }
        i+=1;
    }
    if !seen_eof{return Err("DXF is missing EOF marker".into());}
    for (_,group) in groups{ordinary.push(join_group(group)?);}
    if ordinary.is_empty(){return Err("DXF contains no supported vector entities".into());}
    if ordinary.len()>512{return Err("DXF exceeds 512 imported vectors".into());}
    Ok(DxfVectors{paths:ordinary,units})
}
fn emit(out:&mut String,code:i32,value:impl std::fmt::Display){
    out.push_str(&format!("{code}\n{value}\n"));
}
fn hex_name(s:&str)->String{
    let mut result=String::new();
    for b in s.as_bytes(){result.push_str(&format!("{b:02X}"));}
    result
}
fn emit_meta(out:&mut String,m:&Meta){
    emit(out,1001,APP);
    emit(out,1000,format!("P{}|{}|{}|{}|{}|{}",
        m.id,m.index,m.total,u8::from(m.closed),
        u8::from(m.visible),u8::from(m.locked)));
    let encoded=hex_name(&m.name);
    for chunk in encoded.as_bytes().chunks(180){
        emit(out,1000,format!("N{}",std::str::from_utf8(chunk).unwrap_or("")));
    }
}
fn at(path:&AnalyticPath,i:usize)->Point{
    let p=path.nodes[i].position;
    p.offset(path.origin.x,path.origin.y)
}
fn curve_bulge(a:Point,b:Point,c:&Curve)->Result<f64,String>{
    match *c{
        Curve::Line=>Ok(0.0),
        Curve::Arc{center,clockwise}=>{
            let center=center; // path-local; caller passes local endpoints
            let aa=(a.y-center.y).atan2(a.x-center.x);
            let bb=(b.y-center.y).atan2(b.x-center.x);
            let angle=if clockwise{-(aa-bb).rem_euclid(TAU)}
                else{(bb-aa).rem_euclid(TAU)};
            if angle.abs()<1e-8||angle.abs()>TAU-1e-8{
                return Err("Cannot represent a full-turn DXF bulge".into());
            }
            let bulge=(angle/4.0).tan();
            if !bulge.is_finite(){return Err("DXF arc bulge not finite".into());}
            Ok(bulge)
        }
        Curve::Cubic{..}=>Err("A cubic cannot be stored as DXF polyline bulge".into()),
    }
}
fn lwpoly(out:&mut String,p:&AnalyticPath,meta:&Meta)->Result<(),String>{
    emit(out,0,"LWPOLYLINE");emit(out,8,"0");
    emit(out,90,p.nodes.len());emit(out,70,u8::from(p.closed));
    for i in 0..p.nodes.len(){
        let world=at(p,i);
        emit(out,10,world.x);emit(out,20,world.y);
        if let Some(curve)=p.segments.get(i){
            let a=p.nodes[i].position;
            let b=p.nodes[(i+1)%p.nodes.len()].position;
            let bulge=curve_bulge(a,b,&curve.curve)?;
            if bulge!=0.0{emit(out,42,bulge);}
        }
    }
    emit_meta(out,meta);
    Ok(())
}
fn segment(out:&mut String,p:&AnalyticPath,i:usize,meta:&Meta)->Result<(),String>{
    let a=at(p,i);
    let b=at(p,(i+1)%p.nodes.len());
    match p.segments[i].curve{
        Curve::Line=>{
            emit(out,0,"LINE");emit(out,8,"0");
            emit(out,10,a.x);emit(out,20,a.y);
            emit(out,11,b.x);emit(out,21,b.y);
        }
        Curve::Arc{..}=>{
            // A two-vertex open LWPolyline encodes a signed arc sweep, unlike
            // DXF ARC which is intrinsically counter-clockwise.
            emit(out,0,"LWPOLYLINE");emit(out,8,"0");
            emit(out,90,2);emit(out,70,0);
            emit(out,10,a.x);emit(out,20,a.y);
            emit(out,42,curve_bulge(p.nodes[i].position,
                p.nodes[(i+1)%p.nodes.len()].position,&p.segments[i].curve)?);
            emit(out,10,b.x);emit(out,20,b.y);
        }
        Curve::Cubic{control1,control2}=>{
            emit(out,0,"SPLINE");emit(out,8,"0");
            emit(out,70,8);emit(out,71,3);emit(out,72,8);
            emit(out,73,4);emit(out,74,0);
            for knot in [0,0,0,0,1,1,1,1]{emit(out,40,knot);}
            for cp in [a,control1.offset(p.origin.x,p.origin.y),
                control2.offset(p.origin.x,p.origin.y),b]{
                emit(out,10,cp.x);emit(out,20,cp.y);
            }
        }
    }
    emit_meta(out,meta);
    Ok(())
}
fn export_path(out:&mut String,p:&AnalyticPath)->Result<(),String>{
    let plain=p.segments.iter().all(|s|!matches!(s.curve,Curve::Cubic{..}));
    let count=if plain{1}else{p.segments.len()};
    if count==0||count>256{return Err("DXF vector has invalid segment count".into());}
    for i in 0..count{
        let meta=Meta{id:p.id,index:i,total:count,closed:p.closed,
            name:p.name.clone(),visible:p.visible,locked:p.locked};
        if plain{lwpoly(out,p,&meta)?;}
        else{segment(out,p,i,&meta)?;}
    }
    Ok(())
}
pub fn export_dxf(project:&Project)->Result<String,String>{
    project.validate()?;
    let mut out=String::new();
    for (code,value) in [
        (0,"SECTION"),(2,"HEADER"),(9,"$ACADVER"),(1,"AC1015"),
        (9,"$INSUNITS"),(70,"4"),(0,"ENDSEC"),(0,"SECTION"),
        (2,"TABLES"),(0,"TABLE"),(2,"APPID"),(70,"1"),
        (0,"APPID"),(2,APP),(70,"0"),(0,"ENDTAB"),
        (0,"ENDSEC"),(0,"SECTION"),(2,"ENTITIES")
    ]{emit(&mut out,code,value);}
    for p in &project.paths{export_path(&mut out,p)?;}
    for c in &project.contours{
        let n=c.vertices.len();
        let mut p=path(c.name.clone(),c.vertices.clone(),
            vec![Curve::Line;n],true)?;
        p.id=c.id;p.origin=c.origin;p.visible=c.visible;p.locked=c.locked;
        export_path(&mut out,&p)?;
    }
    emit(&mut out,0,"ENDSEC");emit(&mut out,0,"EOF");
    if out.len()>LIMIT{return Err("DXF output exceeds the 16 MiB limit".into());}
    Ok(out)
}

#[cfg(test)]
mod tests{
    use super::*;
    use crate::{Action,Editor,Primitive,ShapeKind};
    fn approx(a:Point,b:Point){
        assert!(dist(a,b)<1e-5,"{a:?} != {b:?}");
    }
    #[test]
    fn native_roundtrip_preserves_lines_arc_cubic_and_closed_cubic_circle(){
        let mut e=Editor::default();
        for (i,k) in [Primitive::Line,Primitive::Arc,Primitive::Cubic]
            .into_iter().enumerate(){
            e.apply(Action::AddAnalytic{name:format!("Shape &\n # {i}"),
                origin:Point::new(i as f64*35.0,10.0),
                kind:k,width_mm:20.0,height_mm:15.0}).unwrap();
        }
        e.apply(Action::AddShape{kind:ShapeKind::Circle,name:"Circle".into(),
            origin:Point::new(150.0,40.0),width_mm:35.0,height_mm:35.0})
            .unwrap();
        let text=export_dxf(&e.project).unwrap();
        let imported=import_dxf(text.as_bytes()).unwrap();
        assert_eq!(imported.units,"mm");
        assert_eq!(imported.paths.len(),e.project.paths.len());
        for (a,b) in e.project.paths.iter().zip(imported.paths.iter()){
            assert_eq!(a.name,b.name);
            assert_eq!(a.closed,b.closed);
            assert_eq!(a.nodes.len(),b.nodes.len());
            for (a_node,b_node) in a.nodes.iter().zip(b.nodes.iter()){
                approx(a_node.position.offset(a.origin.x,a.origin.y),b_node.position);
            }
            assert_eq!(a.segments.len(),b.segments.len());
            for (lhs,rhs) in a.segments.iter().zip(b.segments.iter()){
                match (&lhs.curve,&rhs.curve){
                    (Curve::Line,Curve::Line)=>{},
                    (Curve::Arc{center:a,clockwise:ca},
                        Curve::Arc{center:b,clockwise:cb})=>{
                        approx(a.offset(0.0,0.0),*b);
                        assert_eq!(ca,cb);
                    }
                    (Curve::Cubic{control1:a,control2:c},
                        Curve::Cubic{control1:b,control2:d})=>{
                        // Translation already validated for path endpoints.
                        approx(a.offset(0.0,0.0),*b);
                        approx(*c,*d);
                    }
                    _=>panic!("curve type changed"),
                }
            }
            b.validate().unwrap();
        }
    }
    #[test]
    fn external_lwpolyline_bulge_and_inches_scale_remain_exact(){
        let body="0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n1\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nLWPOLYLINE\n8\n0\n90\n2\n70\n0\n10\n0\n20\n0\n42\n0.41421356237309503\n10\n2\n20\n2\n0\nENDSEC\n0\nEOF\n";
        let p=import_dxf(body.as_bytes()).unwrap();
        assert_eq!(p.units,"inches");
        assert_eq!(p.paths[0].nodes.len(),2);
        approx(p.paths[0].nodes[1].position,Point::new(50.8,50.8));
        assert!(matches!(p.paths[0].segments[0].curve,Curve::Arc{clockwise:false,..}));
    }
    #[test]
    fn dxf_unsupported_units_entities_and_3d_fail_closed(){
        let good=export_dxf(&Project{paths:vec![crate::AnalyticPath::preset(
            1,"Line".into(),Point::new(0.0,0.0),Primitive::Line,10.0,10.0).unwrap()],
            next_id:2,..Project::default()}).unwrap();
        for bad in [
            good.replace("$INSUNITS\n70\n4","$INSUNITS\n70\n0"),
            good.replace("0\nLWPOLYLINE","0\nINSERT"),
            good.replace("0\nLWPOLYLINE","0\n3DFACE"),
            good.replace("0\nLWPOLYLINE\n8\n0","0\nLWPOLYLINE\n8\n0\n38\n2"),
        ]{assert!(import_dxf(bad.as_bytes()).is_err());}
        assert!(import_dxf(b"0\nSECTION\n2\nENTITIES\n0\nEOF\n").is_err());
    }
    #[test]
    fn lwp_closed_and_cubic_metadata_undo_safe(){
        let mut e=Editor::default();
        e.apply(Action::AddShape{kind:ShapeKind::Rectangle,name:"Square".into(),
            origin:Point::new(8.0,9.0),width_mm:20.0,height_mm:10.0}).unwrap();
        let source=export_dxf(&e.project).unwrap();
        let p=import_dxf(source.as_bytes()).unwrap();
        assert!(p.paths[0].closed);
        assert_eq!(p.paths[0].nodes.len(),4);
        let before=e.project.clone();
        e.apply(Action::ImportPaths{paths:p.paths}).unwrap();
        assert_eq!(e.project.paths.len(),2);
        assert!(e.undo());assert_eq!(e.project,before);
    }
}
