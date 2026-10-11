//! Exact intersection splitting; only line sources with strictly
//! transverse, interior/interior crossing points may reconstruct.
use carvefoundry_core::{Action,Editor,Point,Project,RegionBoolean,Curve,
    boolean_region_boundaries,polygon_contains};
fn rect(editor:&mut Editor,name:&str,lo:Point,hi:Point,reverse:bool)->u64{
    let id=editor.project.next_id;
    let mut pts=vec![Point::new(lo.x,lo.y),Point::new(hi.x,lo.y),
        Point::new(hi.x,hi.y),Point::new(lo.x,hi.y)];
    if reverse{pts.reverse();}
    editor.apply(Action::AddPolyline{name:name.into(),closed:true,points:pts}).unwrap();
    id
}
fn base(reverse_b:bool)->Editor{
    let mut e=Editor::default();
    let a=rect(&mut e,"A",Point::new(0.0,0.0),Point::new(100.0,100.0),false);
    let b=rect(&mut e,"B",Point::new(50.0,50.0),Point::new(150.0,150.0),reverse_b);
    // Saved regions deliberately need 2+ source paths. Keep
    // their added holes well away from crossing segments.
    let ha=rect(&mut e,"A hole",Point::new(10.0,10.0),
        Point::new(30.0,30.0),false);
    let hb=rect(&mut e,"B hole",Point::new(120.0,120.0),
        Point::new(130.0,130.0),true);
    e.apply(Action::SaveCompoundRegion{
        ids:vec![a,ha],name:"First plate".into()}).unwrap();
    e.apply(Action::SaveCompoundRegion{
        ids:vec![b,hb],name:"Second plate".into()}).unwrap();
    assert_eq!(e.project.compound_regions[0].id,5);
    assert_eq!(e.project.compound_regions[1].id,6);
    e
}
fn run(e:&mut Editor,operation:RegionBoolean){
    e.apply(Action::BooleanRegions{left_region_id:5,
        right_region_id:6,operation,name:"Exact overlap".into()}).unwrap();
}
#[test]
fn overlapping_rectangles_union_exact_source_edges_and_holes(){
    let mut e=base(false);
    let original=e.project.clone();
    run(&mut e,RegionBoolean::Union);
    assert_eq!(e.project.paths.len(),7);
    let result=e.project.compound_regions.last().unwrap().id;
    assert_eq!(e.project.compound_regions.last().unwrap().path_ids.len(),3);
    for (point,want) in [
        (Point::new(5.0,5.0),true),
        (Point::new(20.0,20.0),false),
        (Point::new(60.0,60.0),true),
        (Point::new(140.0,140.0),true),
        (Point::new(125.0,125.0),false),
        (Point::new(200.0,200.0),false),
    ]{
        assert_eq!(e.project.compound_material_at(result,point).unwrap(),want);
    }
    assert!(e.project.paths[4..].iter()
        .flat_map(|p|p.segments.iter()).all(|s|matches!(s.curve,Curve::Line)));
    assert_eq!(e.project.paths[..4],original.paths);
    let bytes=e.project.encode().unwrap();
    assert_eq!(Project::decode(&bytes).unwrap(),e.project);
    assert!(e.undo());assert_eq!(e.project,original);
    assert!(e.redo());assert_eq!(Project::decode(&e.project.encode().unwrap()).unwrap(),e.project);
}
#[test]
fn transverse_intersection_and_differences_reconstruct_expected_material(){
    for reversed in [false,true]{
        for (operation,checks) in [
            (RegionBoolean::Intersection,[
                (Point::new(75.0,75.0),true),
                (Point::new(20.0,20.0),false),
                (Point::new(110.0,110.0),false)]),
            (RegionBoolean::Difference,[
                (Point::new(5.0,5.0),true),
                (Point::new(20.0,20.0),false),
                (Point::new(75.0,75.0),false)]),
        ]{
            let mut e=base(reversed);
            let original=e.project.clone();
            run(&mut e,operation);
            assert!(e.project.paths.len()>original.paths.len());
            let generated=e.project.paths.len()-original.paths.len();
            if generated>1{
                let last=e.project.compound_regions.last().unwrap();
                assert_eq!(last.path_ids.len(),generated);
            }else{
                assert_eq!(e.project.compound_regions.len(),2,
                    "One output loop is a standalone editable path, not an extra saved region");
            }
            for (point,expected) in checks{
                let is_material=if generated>1{
                    let last=e.project.compound_regions.last().unwrap();
                    e.project.compound_material_at(last.id,point).unwrap()
                }else{
                    let loop_path=&e.project.paths[4];
                    let world=loop_path.nodes.iter().map(|n|
                        n.position.offset(loop_path.origin.x,loop_path.origin.y)
                    ).collect::<Vec<_>>();
                    polygon_contains(&world,point)
                };
                assert_eq!(is_material,expected,
                    "reversed {reversed} op {operation:?} at {point:?}");
            }
            assert_eq!(e.project.paths[..4],original.paths);
        }
    }
}
#[test]
fn reversed_operands_change_subtraction_but_not_source_geometry(){
    let mut e=base(true);
    let before=e.project.clone();
    e.apply(Action::BooleanRegions{
        left_region_id:6,right_region_id:5,
        operation:RegionBoolean::Difference,name:"B less A".into(),
    }).unwrap();
    let last=e.project.compound_regions.last().unwrap().id;
    assert!(e.project.compound_material_at(last,Point::new(145.0,145.0)).unwrap());
    assert!(!e.project.compound_material_at(last,Point::new(75.0,75.0)).unwrap());
    assert!(!e.project.compound_material_at(last,Point::new(125.0,125.0)).unwrap());
    assert_eq!(e.project.paths[..4],before.paths);
}
#[test]
fn same_height_collinear_overlap_or_corner_touch_refuses_all_operations(){
    for (lo,hi) in [
        (Point::new(50.0,0.0),Point::new(150.0,100.0)),
        (Point::new(100.0,100.0),Point::new(200.0,200.0)),
        (Point::new(100.0,40.0),Point::new(200.0,140.0)),
    ]{
        let mut e=Editor::default();
        let a=rect(&mut e,"A",Point::new(0.0,0.0),Point::new(100.0,100.0),false);
        let ha=rect(&mut e,"hole A",Point::new(10.0,10.0),Point::new(20.0,20.0),false);
        let b=rect(&mut e,"B",lo,hi,false);
        let hb=rect(&mut e,"hole B",Point::new(lo.x+10.0,lo.y+10.0),
            Point::new(lo.x+20.0,lo.y+20.0),false);
        e.apply(Action::SaveCompoundRegion{ids:vec![a,ha],name:"A".into()}).unwrap();
        e.apply(Action::SaveCompoundRegion{ids:vec![b,hb],name:"B".into()}).unwrap();
        let saved=e.project.clone();
        for op in [RegionBoolean::Union,RegionBoolean::Intersection,RegionBoolean::Difference]{
            assert!(e.apply(Action::BooleanRegions{
                left_region_id:5,right_region_id:6,operation:op,name:"Bad".into()}).is_err());
            assert_eq!(e.project,saved);
        }
    }
}
#[test]
fn near_touching_crossings_and_tiny_slivers_refuse_atomically(){
    // Almost coincident crossings at a vertex should not be snapped
    // into a fabricated topology or leave partial edits.
    let mut e=Editor::default();
    rect(&mut e,"A",Point::new(0.0,0.0),Point::new(100.0,100.0),false);
    rect(&mut e,"A hole",Point::new(10.0,10.0),Point::new(20.0,20.0),false);
    rect(&mut e,"B",Point::new(99.9999999,40.0),Point::new(150.0,150.0),false);
    rect(&mut e,"B hole",Point::new(120.0,120.0),Point::new(130.0,130.0),false);
    e.apply(Action::SaveCompoundRegion{ids:vec![1,2],name:"A".into()}).unwrap();
    e.apply(Action::SaveCompoundRegion{ids:vec![3,4],name:"B".into()}).unwrap();
    let saved=e.project.clone();
    assert!(boolean_region_boundaries(&e.project,5,6,RegionBoolean::Union).is_err());
    assert_eq!(e.project,saved);
}
