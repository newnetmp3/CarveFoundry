//! Source-analytic compound CAD hole/island validation. Read-only:
 //! no 2.5D toolpath region or machine-clearance semantics.
use carvefoundry_core::{
    analyze_compound_paths,AnalyticPath,CompoundRole,Curve,
    PathNode,PathSegment,Point,Primitive,Project,polyline,
    import_svg,import_dxf,
};
fn square(id:u64,lo:f64,hi:f64,reverse:bool)->AnalyticPath{
    let mut coords=vec![
        Point::new(lo,lo),Point::new(hi,lo),
        Point::new(hi,hi),Point::new(lo,hi),
    ];
    if reverse{coords.reverse();}
    polyline(id,format!("Square #{id}"),Point::new(0.0,0.0),coords,true).unwrap()
}
fn circle(id:u64,c:Point,r:f64,clockwise:bool)->AnalyticPath{
    let mut pts=vec![
        Point::new(c.x+r,c.y),Point::new(c.x,c.y+r),
        Point::new(c.x-r,c.y),Point::new(c.x,c.y-r),
    ];
    if clockwise{pts.reverse();}
    let path=AnalyticPath{
        id,name:format!("Circle #{id}"),origin:Point::new(0.0,0.0),
        visible:true,locked:false,closed:true,
        nodes:pts.drain(..).enumerate().map(|(i,position)|PathNode{
            id:i as u64+1,position}).collect(),
        segments:(0..4).map(|i|PathSegment{
            id:i+5,curve:Curve::Arc{center:c,clockwise}
        }).collect(),
        next_element_id:9,
    };
    path.validate().unwrap();
    path
}
fn check(paths:&[AnalyticPath],id:u64,depth:usize,parent:Option<u64>,
    role:CompoundRole){
    let hierarchy=analyze_compound_paths(paths).unwrap();
    let entry=hierarchy.iter().find(|x|x.path_id==id).unwrap();
    assert_eq!(entry.depth,depth);
    assert_eq!(entry.parent_path_id,parent);
    assert_eq!(entry.role,role);
}
#[test]
fn deep_holes_and_islands_are_parity_classified_regardless_of_winding_order(){
    let paths=vec![
        square(3,35.0,65.0,true),
        square(1,0.0,100.0,true),
        square(4,42.0,58.0,false),
        square(2,20.0,80.0,false),
    ];
    check(&paths,1,0,None,CompoundRole::Outline);
    check(&paths,2,1,Some(1),CompoundRole::Hole);
    check(&paths,3,2,Some(2),CompoundRole::Outline);
    check(&paths,4,3,Some(3),CompoundRole::Hole);
    assert_eq!(paths[0].nodes[0].position,Point::new(35.0,65.0),
        "Analysis must not rewrite reversed source");
}
#[test]
fn multiple_disconnected_outlines_and_holes_have_correct_immediate_parents(){
    let outer=square(1,0.0,100.0,false);
    let inner=square(2,10.0,20.0,true);
    let distant=square(3,150.0,190.0,true);
    let paths=vec![distant,inner,outer];
    check(&paths,1,0,None,CompoundRole::Outline);
    check(&paths,2,1,Some(1),CompoundRole::Hole);
    check(&paths,3,0,None,CompoundRole::Outline);
}
#[test]
fn concentric_true_circular_loops_and_nested_island_are_analytically_classified(){
    let paths=vec![
        circle(1,Point::new(80.0,80.0),50.0,false),
        circle(2,Point::new(80.0,80.0),30.0,true),
        circle(3,Point::new(80.0,80.0),10.0,false)
    ];
    check(&paths,1,0,None,CompoundRole::Outline);
    check(&paths,2,1,Some(1),CompoundRole::Hole);
    check(&paths,3,2,Some(2),CompoundRole::Outline);
}
#[test]
fn exact_circle_nested_in_square_and_square_nested_in_circle(){
    let path_a=vec![square(1,0.0,100.0,true),
        circle(2,Point::new(50.0,50.0),10.0,true)];
    check(&path_a,2,1,Some(1),CompoundRole::Hole);
    let path_b=vec![circle(1,Point::new(50.0,50.0),45.0,false),
        square(2,40.0,60.0,true)];
    check(&path_b,2,1,Some(1),CompoundRole::Hole);
}
#[test]
fn independently_authored_svg_and_dxf_capsules_support_rectangular_hole(){
    let outer_svg=include_str!("fixtures/capsule_external.svg");
    let outer_dxf=include_str!("fixtures/capsule_external.dxf");
    let first=import_svg(outer_svg.as_bytes()).unwrap().paths.remove(0);
    let second=import_dxf(outer_dxf.as_bytes()).unwrap().paths.remove(0);
    let hole=polyline(3,"Rectangle hole".into(),Point::new(0.0,0.0),
        vec![Point::new(52.0,50.0),Point::new(88.0,50.0),
             Point::new(88.0,70.0),Point::new(52.0,70.0)],true).unwrap();
    for mut outer in [first,second]{
        outer.id=2;
        let paths=vec![hole.clone(),outer];
        check(&paths,3,1,Some(2),CompoundRole::Hole);
    }
}
#[test]
fn crossing_overlapping_touching_and_coincident_boundaries_reject(){
    let original=square(1,0.0,100.0,false);
    let crossing=square(2,90.0,110.0,false);
    let share_edge=square(2,100.0,120.0,true);
    // One corner lies on another boundary, but no segment is shared.
    let corner=polyline(2,"Vertex tangent".into(),Point::new(0.0,0.0),
        vec![Point::new(100.0,100.0),Point::new(110.0,120.0),
             Point::new(120.0,110.0)],true).unwrap();
    let coincident=square(2,0.0,100.0,true);
    for invalid in [crossing,share_edge,corner,coincident]{
        let error=analyze_compound_paths(&[original.clone(),invalid]).unwrap_err();
        assert!(error.contains("cross")||error.contains("touch")
            ||error.contains("coincident"),"{error}");
    }
    assert_eq!(original.nodes[0].position,Point::new(0.0,0.0));
}
#[test]
fn circle_line_tangency_refuses_as_hole_without_guessing_clearance(){
    let outer=square(1,0.0,100.0,false);
    let tangent=circle(2,Point::new(90.0,50.0),10.0,true);
    let err=analyze_compound_paths(&[outer,tangent]).unwrap_err();
    assert!(err.contains("touch")||err.contains("cross"),"{err}");
}
#[test]
fn invalid_non_simple_parent_cubic_or_open_source_fail_closed(){
    let bowtie=polyline(1,"Bow tie".into(),Point::new(0.0,0.0),
        vec![Point::new(0.0,0.0),Point::new(100.0,100.0),
             Point::new(0.0,100.0),Point::new(100.0,0.0)],true);
    assert!(bowtie.is_err(),"Simple contour constructor must reject area-zero bowtie");
    let cub=AnalyticPath::preset(1,"Bezier".into(),
        Point::new(0.0,0.0),Primitive::Cubic,20.0,20.0).unwrap();
    let err=analyze_compound_paths(&[cub]).unwrap_err();
    assert!(err.contains("open"),"{err}");
    let mut cubclosed=square(1,0.0,100.0,false);
    cubclosed.segments[0].curve=Curve::Cubic{
        control1:Point::new(20.0,-10.0),
        control2:Point::new(80.0,-10.0)
    };
    assert!(analyze_compound_paths(&[cubclosed]).unwrap_err().contains("cubic"));
}
#[test]
fn duplicate_ids_and_unsafe_size_reject_without_project_mutation(){
    let p=square(1,0.0,100.0,false);
    assert!(analyze_compound_paths(&[p.clone(),p.clone()]).unwrap_err()
        .contains("duplicate"));
    let paths=(0..33).map(|i|square(i+1,0.0,100.0,false))
        .collect::<Vec<_>>();
    assert!(analyze_compound_paths(&paths).unwrap_err().contains("1–32"));
    let project=Project{next_id:2,paths:vec![p.clone()],..Project::default()};
    let before=project.clone();
    let roles=analyze_compound_paths(&project.paths).unwrap();
    assert_eq!(roles.len(),1);
    assert_eq!(roles[0].role,CompoundRole::Outline);
    assert_eq!(project,before);
}
