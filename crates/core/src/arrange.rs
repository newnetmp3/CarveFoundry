//! Precision CAD arrangement, using retained curves rather than preview pixels.
//! Pure geometry: no selection UI, controller, toolpath or NC dependencies.
use crate::{Curve,Point,Project};
use std::f64::consts::{FRAC_PI_2,TAU};

#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Bounds{pub min:Point,pub max:Point}
impl Bounds {
    fn new(p:Point)->Self{Self{min:p,max:p}}
    fn include(&mut self,p:Point){
        self.min.x=self.min.x.min(p.x);
        self.min.y=self.min.y.min(p.y);
        self.max.x=self.max.x.max(p.x);
        self.max.y=self.max.y.max(p.y);
    }
    pub fn center(self)->Point{
        Point::new((self.min.x+self.max.x)*0.5,(self.min.y+self.max.y)*0.5)
    }
    pub fn width(self)->f64{self.max.x-self.min.x}
    pub fn height(self)->f64{self.max.y-self.min.y}
}
fn cubic(p0:f64,p1:f64,p2:f64,p3:f64,t:f64)->f64{
    let u=1.0-t;
    u*u*u*p0+3.0*u*u*t*p1+3.0*u*t*t*p2+t*t*t*p3
}
fn cubic_extrema(a:f64,b:f64,c:f64,d:f64)->Vec<f64>{
    // Derivative / 3: A t² + B t + C = 0.
    let aa=-a+3.0*b-3.0*c+d;
    let bb=2.0*(a-2.0*b+c);
    let cc=b-a;
    if aa.abs()<1e-12{
        if bb.abs()<1e-12{return vec![];}
        let t=-cc/bb;
        return if (0.0..1.0).contains(&t){vec![t]}else{vec![]};
    }
    let discriminant=bb*bb-4.0*aa*cc;
    if discriminant<0.0{return vec![];}
    let r=discriminant.sqrt();
    [(-bb-r)/(2.0*aa),(-bb+r)/(2.0*aa)]
        .into_iter().filter(|t|(0.0..1.0).contains(t)).collect()
}
/// Exact source-space bounding box of retained line, circular arc and cubic
/// Bezier segments. No tessellation-derived false precision for layout tools.
pub fn vector_bounds(project:&Project,id:u64)->Result<Bounds,String>{
    if let Some(path)=project.paths.iter().find(|p|p.id==id){
        let first=path.nodes.first().ok_or("Path has no nodes")?;
        let mut bounds=Bounds::new(first.position);
        for (i,s) in path.segments.iter().enumerate(){
            let a=path.nodes[i].position;
            let b=path.nodes[(i+1)%path.nodes.len()].position;
            bounds.include(a);bounds.include(b);
            match s.curve{
                Curve::Line=>{},
                Curve::Arc{center,clockwise}=>{
                    let radius=(a.x-center.x).hypot(a.y-center.y);
                    let begin=(a.y-center.y).atan2(a.x-center.x);
                    let end=(b.y-center.y).atan2(b.x-center.x);
                    let sweep=if clockwise{
                        (begin-end).rem_euclid(TAU)
                    }else{(end-begin).rem_euclid(TAU)};
                    for k in 0..4{
                        let angle=k as f64*FRAC_PI_2;
                        let along=if clockwise{
                            (begin-angle).rem_euclid(TAU)
                        }else{(angle-begin).rem_euclid(TAU)};
                        if along<=sweep+1e-10{
                            bounds.include(Point::new(
                                center.x+radius*angle.cos(),
                                center.y+radius*angle.sin()));
                        }
                    }
                }
                Curve::Cubic{control1,control2}=>{
                    for t in cubic_extrema(a.x,control1.x,control2.x,b.x){
                        bounds.include(Point::new(
                            cubic(a.x,control1.x,control2.x,b.x,t),
                            cubic(a.y,control1.y,control2.y,b.y,t)));
                    }
                    for t in cubic_extrema(a.y,control1.y,control2.y,b.y){
                        bounds.include(Point::new(
                            cubic(a.x,control1.x,control2.x,b.x,t),
                            cubic(a.y,control1.y,control2.y,b.y,t)));
                    }
                }
            }
        }
        return Ok(Bounds{
            min:bounds.min.offset(path.origin.x,path.origin.y),
            max:bounds.max.offset(path.origin.x,path.origin.y),
        });
    }
    if let Some(contour)=project.contours.iter().find(|p|p.id==id){
        let mut points=contour.world_points().into_iter();
        let mut bounds=Bounds::new(points.next().ok_or("Contour has no vertices")?);
        for p in points{bounds.include(p);}
        return Ok(bounds);
    }
    Err("Selected vector ID does not exist".into())
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Arrangement {
    Left, HCenter, Right, Bottom, VCenter, Top,
    DistributeX, DistributeY,
    StockLeft, StockHCenter, StockRight,
    StockBottom, StockVCenter, StockTop,
}
impl Arrangement {
    pub const fn title(self)->&'static str{
        match self {
            Self::Left=>"Align left", Self::HCenter=>"Align horizontal centers",
            Self::Right=>"Align right",Self::Bottom=>"Align bottom",
            Self::VCenter=>"Align vertical centers",Self::Top=>"Align top",
            Self::DistributeX=>"Distribute horizontally",
            Self::DistributeY=>"Distribute vertically",
            Self::StockLeft=>"To stock left",Self::StockHCenter=>"To stock center X",
            Self::StockRight=>"To stock right",Self::StockBottom=>"To stock bottom",
            Self::StockVCenter=>"To stock center Y",Self::StockTop=>"To stock top",
        }
    }
}
fn val(b:Bounds,mode:Arrangement)->f64{
    match mode{
        Arrangement::Left|Arrangement::StockLeft=>b.min.x,
        Arrangement::Right|Arrangement::StockRight=>b.max.x,
        Arrangement::HCenter|Arrangement::StockHCenter|Arrangement::DistributeX=>b.center().x,
        Arrangement::Bottom|Arrangement::StockBottom=>b.min.y,
        Arrangement::Top|Arrangement::StockTop=>b.max.y,
        Arrangement::VCenter|Arrangement::StockVCenter|Arrangement::DistributeY=>b.center().y,
    }
}
fn x_axis(mode:Arrangement)->bool{
    matches!(mode,Arrangement::Left|Arrangement::HCenter|Arrangement::Right
        |Arrangement::DistributeX|Arrangement::StockLeft
        |Arrangement::StockHCenter|Arrangement::StockRight)
}
fn is_stock(mode:Arrangement)->bool{
    matches!(mode,Arrangement::StockLeft|Arrangement::StockHCenter|
        Arrangement::StockRight|Arrangement::StockBottom|
        Arrangement::StockVCenter|Arrangement::StockTop)
}
/// Return (ID, displacement) pairs without mutating project. Multiple-item
/// alignment uses the full selection's extremal edge / center; Stock modes
/// move the entire selection AS ONE GROUP without collapsing its spacing.
pub fn arrangement_offsets(project:&Project,ids:&[u64],mode:Arrangement)
    ->Result<Vec<(u64,Point)>,String>{
    if ids.is_empty(){return Err("No selected vectors to arrange".into());}
    let mut bounds=Vec::with_capacity(ids.len());
    for &id in ids{bounds.push((id,vector_bounds(project,id)?));}
    let is_x=x_axis(mode);
    if matches!(mode,Arrangement::DistributeX|Arrangement::DistributeY){
        if bounds.len()<3{return Err("Distribute requires at least three vectors".into());}
        bounds.sort_by(|a,b|{
            val(a.1,mode).total_cmp(&val(b.1,mode)).then(a.0.cmp(&b.0))
        });
        let first=val(bounds[0].1,mode);
        let last=val(bounds[bounds.len()-1].1,mode);
        let step=(last-first)/(bounds.len()-1) as f64;
        return Ok(bounds.iter().enumerate().map(|(i,(id,b))|{
            let delta=first+step*i as f64-val(*b,mode);
            (*id,if is_x{Point::new(delta,0.0)}
                else{Point::new(0.0,delta)})
        }).collect());
    }
    let target=if is_stock(mode){
        let group_min=bounds.iter().map(|(_,b)|if is_x{b.min.x}else{b.min.y})
            .fold(f64::INFINITY,f64::min);
        let group_max=bounds.iter().map(|(_,b)|if is_x{b.max.x}else{b.max.y})
            .fold(f64::NEG_INFINITY,f64::max);
        // Stock target for matching group boundary or center.
        let dim=if is_x{project.stock.width_mm}else{project.stock.height_mm};
        let where_to=match mode{
            Arrangement::StockLeft|Arrangement::StockBottom=>0.0,
            Arrangement::StockRight|Arrangement::StockTop=>dim,
            _=>dim*0.5,
        };
        let current=match mode{
            Arrangement::StockLeft|Arrangement::StockBottom=>group_min,
            Arrangement::StockRight|Arrangement::StockTop=>group_max,
            _=>(group_min+group_max)*0.5,
        };
        let delta=where_to-current;
        return Ok(bounds.iter().map(|(id,_)|(*id,
            if is_x{Point::new(delta,0.0)}else{Point::new(0.0,delta)}
        )).collect());
    }else{
        match mode{
            Arrangement::Left|Arrangement::Bottom=>bounds.iter()
                .map(|(_,b)|val(*b,mode)).fold(f64::INFINITY,f64::min),
            Arrangement::Right|Arrangement::Top=>bounds.iter()
                .map(|(_,b)|val(*b,mode)).fold(f64::NEG_INFINITY,f64::max),
            _=>{
                let min=bounds.iter().map(|(_,b)|val(*b,mode))
                    .fold(f64::INFINITY,f64::min);
                let max=bounds.iter().map(|(_,b)|val(*b,mode))
                    .fold(f64::NEG_INFINITY,f64::max);
                (min+max)*0.5
            }
        }
    };
    Ok(bounds.into_iter().map(|(id,b)|{
        let delta=target-val(b,mode);
        (id,if is_x{Point::new(delta,0.0)}
            else{Point::new(0.0,delta)})
    }).collect())
}

#[cfg(test)]
mod tests{
    use super::*;
    use crate::{Action,Editor,ShapeKind,Primitive};
    #[test]
    fn exact_bezier_extrema_are_not_control_points(){
        let mut e=Editor::default();
        e.apply(Action::AddAnalytic{name:"Cubic".into(),
            origin:Point::new(12.0,7.0),kind:Primitive::Cubic,
            width_mm:100.0,height_mm:40.0}).unwrap();
        let b=vector_bounds(&e.project,1).unwrap();
        // symmetric two controls at y=40: true maximum = 30, not 40.
        assert!((b.max.y-37.0).abs()<1e-9);
        assert_eq!(b.min.y,7.0);
        assert_eq!(b.min.x,12.0);
        assert_eq!(b.max.x,112.0);
    }
    #[test]
    fn true_arc_bounds_include_internal_quadrant(){
        let mut e=Editor::default();
        e.apply(Action::AddAnalytic{name:"Arc".into(),
            origin:Point::new(5.0,15.0),kind:Primitive::Arc,
            width_mm:50.0,height_mm:20.0}).unwrap();
        let b=vector_bounds(&e.project,1).unwrap();
        assert!((b.min.x-5.0).abs()<1e-9);
        assert!((b.max.x-55.0).abs()<1e-9);
        assert!((b.max.y-40.0).abs()<1e-9);
    }
    #[test]
    fn layout_align_and_distribute_preserve_relative_shapes(){
        let mut e=Editor::default();
        for (x,y) in [(10.0,10.0),(70.0,25.0),(130.0,40.0)]{
            e.apply(Action::AddShape{kind:ShapeKind::Rectangle,
                name:format!("Panel {x}"),origin:Point::new(x,y),
                width_mm:20.0,height_mm:10.0}).unwrap();
        }
        let move_y=arrangement_offsets(&e.project,&[1,2,3],
            Arrangement::Bottom).unwrap();
        assert_eq!(move_y[0].1,Point::new(0.0,0.0));
        assert_eq!(move_y[1].1,Point::new(0.0,-15.0));
        assert_eq!(move_y[2].1,Point::new(0.0,-30.0));
        let dist=arrangement_offsets(&e.project,&[1,2,3],
            Arrangement::DistributeX).unwrap();
        assert!(dist.iter().all(|(_,delta)|delta.x.abs()<1e-9));
        let stock=arrangement_offsets(&e.project,&[1,2,3],
            Arrangement::StockHCenter).unwrap();
        assert!(stock.windows(2).all(|w|w[0].1==w[1].1));
        assert!(arrangement_offsets(&e.project,&[1,2],
            Arrangement::DistributeY).is_err());
    }
}
