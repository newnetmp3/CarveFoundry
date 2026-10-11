//! True-source Boolean operations on disjoint or nested CAD region loops.
//! No sampled geometry, no region-to-toolpath conversion.
use carvefoundry_core::{
    Action,AnalyticPath,Curve,Editor,PathNode,PathSegment,Point,
    Project,RegionBoolean,
    boolean_region_boundaries,import_svg,import_dxf
};
fn box_path(editor:&mut Editor,lo:f64,hi:f64){
    editor.apply(Action::AddPolyline{
        name:format!("Box {lo} {hi}"),closed:true,
        points:vec![Point::new(lo,lo),Point::new(hi,lo),
            Point::new(hi,hi),Point::new(lo,hi)],
    }).unwrap();
}
fn nested_pair()->Editor{
    let mut editor=Editor::default();
    box_path(&mut editor,0.0,100.0); // A exterior
    box_path(&mut editor,20.0,80.0); // A hole
    box_path(&mut editor,10.0,90.0); // B exterior
    box_path(&mut editor,30.0,70.0); // B hole
    editor.apply(Action::SaveCompoundRegion{
        ids:vec![1,2],name:"A ring".into()}).unwrap();
    editor.apply(Action::SaveCompoundRegion{
        ids:vec![3,4],name:"B ring".into()}).unwrap();
    assert_eq!(editor.project.compound_regions[0].id,5);
    assert_eq!(editor.project.compound_regions[1].id,6);
    editor
}
fn apply(editor:&mut Editor,kind:RegionBoolean){
    editor.apply(Action::BooleanRegions{
        left_region_id:5,right_region_id:6,operation:kind,
        name:"Boolean panel".into(),
    }).unwrap();
}
#[test]
fn exact_union_of_nested_donuts_preserves_outer_and_innermost_hole(){
    let mut e=nested_pair();
    let saved=e.project.clone();
    apply(&mut e,RegionBoolean::Union);
    assert_eq!(e.project.paths.len(),saved.paths.len()+2);
    let generated=&e.project.paths[4..];
    assert_eq!(generated[0].segments,saved.paths[0].segments);
    assert_eq!(generated[1].segments,saved.paths[3].segments);
    assert_eq!(generated[0].nodes,saved.paths[0].nodes);
    assert_eq!(generated[1].nodes,saved.paths[3].nodes);
    assert_eq!(generated[0].id,7);
    assert_eq!(generated[1].id,8);
    assert!(generated.iter().all(|p|p.visible&&!p.locked));
    let result=e.project.compound_regions.last().unwrap();
    assert_eq!(result.id,9);
    assert_eq!(result.path_ids,vec![7,8]);
    assert_eq!(result.parent_path_ids,vec![None,Some(7)]);
    for (point,want) in [
        (Point::new(5.0,5.0),true),
        (Point::new(25.0,25.0),true),
        (Point::new(50.0,50.0),false),
        (Point::new(120.0,50.0),false),
    ]{
        assert_eq!(e.project.compound_material_at(9,point).unwrap(),want);
    }
    assert_eq!(Project::decode(&e.project.encode().unwrap()).unwrap(),e.project);
    assert!(e.undo());
    assert_eq!(e.project,saved);
    assert!(e.redo());
    assert_eq!(e.project.compound_regions.last().unwrap().id,9);
}
#[test]
fn exact_intersection_and_difference_choose_different_original_loops(){
    for (operation,expected_source_indices,points) in [
        (RegionBoolean::Intersection,[1,2],[
            (Point::new(5.0,5.0),false),
            (Point::new(15.0,15.0),true),
            (Point::new(25.0,25.0),false)]),
        (RegionBoolean::Difference,[0,2],[
            (Point::new(5.0,5.0),true),
            (Point::new(15.0,15.0),false),
            (Point::new(50.0,50.0),false)]),
    ]{
        let mut e=nested_pair();
        let original=e.project.paths.clone();
        apply(&mut e,operation);
        assert_eq!(e.project.paths.len(),6);
        for (actual,expected) in e.project.paths[4..]
            .iter().zip(expected_source_indices){
            assert_eq!(actual.nodes,original[expected].nodes);
            assert_eq!(actual.segments,original[expected].segments);
        }
        let region=e.project.compound_regions.last().unwrap().id;
        for (point,expect_material) in points{
            assert_eq!(e.project.compound_material_at(region,point).unwrap(),
                expect_material,"Boolean {operation:?} at {point:?}");
        }
        assert_eq!(e.project.paths[..4],original);
    }
}
#[test]
fn swapped_difference_is_a_distinct_source_faithful_result(){
    let mut e=nested_pair();
    e.apply(Action::BooleanRegions{
        left_region_id:6,right_region_id:5,
        operation:RegionBoolean::Difference,
        name:"B minus A".into(),
    }).unwrap();
    let result=e.project.compound_regions.last().unwrap().id;
    // Only B's inner material inside A's hole survives.
    assert_eq!(e.project.paths.len(),6);
    assert_eq!(e.project.paths[4].nodes,e.project.paths[3].nodes);
    assert_eq!(e.project.paths[5].nodes,e.project.paths[1].nodes);
    assert!(e.project.compound_material_at(result,Point::new(25.0,25.0)).unwrap());
    assert!(!e.project.compound_material_at(result,Point::new(50.0,50.0)).unwrap());
    assert!(!e.project.compound_material_at(result,Point::new(15.0,15.0)).unwrap());
}
#[test]
fn disjoint_donuts_union_keeps_all_source_loops_while_intersection_refuses_empty(){
    let mut e=Editor::default();
    box_path(&mut e,0.0,100.0);box_path(&mut e,20.0,40.0);
    box_path(&mut e,150.0,250.0);box_path(&mut e,170.0,190.0);
    e.apply(Action::SaveCompoundRegion{ids:vec![1,2],name:"A".into()}).unwrap();
    e.apply(Action::SaveCompoundRegion{ids:vec![3,4],name:"B".into()}).unwrap();
    let old=e.project.clone();
    e.apply(Action::BooleanRegions{
        left_region_id:5,right_region_id:6,
        operation:RegionBoolean::Union,name:"Two donuts".into(),
    }).unwrap();
    let compound=e.project.compound_regions.last().unwrap();
    assert_eq!(compound.path_ids.len(),4);
    assert_eq!(compound.parent_path_ids,vec![None,Some(7),None,Some(9)]);
    assert!(e.project.compound_material_at(compound.id,Point::new(5.0,5.0)).unwrap());
    assert!(e.project.compound_material_at(compound.id,Point::new(155.0,155.0)).unwrap());
    assert!(!e.project.compound_material_at(compound.id,Point::new(30.0,30.0)).unwrap());
    assert!(e.undo());
    assert_eq!(e.project,old);
    let result=boolean_region_boundaries(&e.project,5,6,
        RegionBoolean::Intersection);
    assert!(result.unwrap_err().contains("empty"));
}
#[test]
fn crossing_and_tangent_sources_reject_atomically_without_approximating(){
    let mut e=Editor::default();
    box_path(&mut e,0.0,100.0);box_path(&mut e,20.0,30.0);
    box_path(&mut e,50.0,150.0);box_path(&mut e,70.0,80.0);
    e.apply(Action::SaveCompoundRegion{ids:vec![1,2],name:"A".into()}).unwrap();
    e.apply(Action::SaveCompoundRegion{ids:vec![3,4],name:"B".into()}).unwrap();
    let saved=e.project.clone();
    for operation in [RegionBoolean::Union,RegionBoolean::Intersection,
        RegionBoolean::Difference]{
        let error=e.apply(Action::BooleanRegions{
            left_region_id:5,right_region_id:6,operation,name:"Unsafe".into(),
        }).unwrap_err();
        assert!(error.contains("cross/touch")||error.contains("cross")
            ||error.contains("touch"),"{error}");
        assert_eq!(e.project,saved);
    }
    // Exact tangent contact remains unsafe even if no areas overlap.
    let mut e=Editor::default();
    box_path(&mut e,0.0,100.0);box_path(&mut e,20.0,30.0);
    box_path(&mut e,100.0,200.0);box_path(&mut e,120.0,130.0);
    e.apply(Action::SaveCompoundRegion{ids:vec![1,2],name:"A".into()}).unwrap();
    e.apply(Action::SaveCompoundRegion{ids:vec![3,4],name:"B".into()}).unwrap();
    assert!(boolean_region_boundaries(&e.project,5,6,
        RegionBoolean::Union).is_err());
}
#[test]
fn missing_same_region_and_invalid_name_refuse_without_change(){
    let mut e=nested_pair();
    let saved=e.project.clone();
    for (a,b) in [(5,5),(6,999),(999,5)]{
        assert!(boolean_region_boundaries(&e.project,a,b,
            RegionBoolean::Union).is_err());
    }
    assert!(e.apply(Action::BooleanRegions{
        left_region_id:5,right_region_id:6,
        operation:RegionBoolean::Union,name:" \t".into(),
    }).is_err());
    assert_eq!(e.project,saved);
}
fn true_circle(id:u64,r:f64)->AnalyticPath{
    let center=Point::new(50.0,50.0);
    let pts=[Point::new(50.0+r,50.0),Point::new(50.0,50.0+r),
        Point::new(50.0-r,50.0),Point::new(50.0,50.0-r)];
    let path=AnalyticPath{
        id,name:format!("Circle radius {r}"),origin:Point::new(0.0,0.0),
        visible:true,locked:false,closed:true,
        nodes:pts.into_iter().enumerate().map(|(i,position)|PathNode{
            id:i as u64+1,position,
        }).collect(),
        segments:(0..4).map(|i|PathSegment{id:i as u64+5,
            curve:Curve::Arc{center,clockwise:false}}).collect(),
        next_element_id:9,
    };
    path.validate().unwrap();
    path
}
#[test]
fn exact_concentric_true_arc_booleans_preserve_full_original_circles(){
    let mut e=Editor::new(Project{
        paths:vec![true_circle(1,45.0),true_circle(2,30.0),
            true_circle(3,40.0),true_circle(4,15.0)],
        next_id:5,..Project::default(),
    }).unwrap();
    e.apply(Action::SaveCompoundRegion{ids:vec![1,2],name:"A".into()}).unwrap();
    e.apply(Action::SaveCompoundRegion{ids:vec![3,4],name:"B".into()}).unwrap();
    for (operation,expected) in [
        (RegionBoolean::Union,[0,3]),
        (RegionBoolean::Intersection,[1,2]),
        (RegionBoolean::Difference,[0,2]),
    ]{
        let mut copy=e.clone();
        copy.apply(Action::BooleanRegions{
            left_region_id:5,right_region_id:6,operation,
            name:"True circle result".into(),
        }).unwrap();
        for (p,old_index) in copy.project.paths[4..].iter().zip(expected){
            assert_eq!(p.segments,e.project.paths[old_index].segments);
            assert_eq!(p.nodes,e.project.paths[old_index].nodes);
            assert!(p.segments.iter().all(|s|matches!(s.curve,Curve::Arc{..})));
        }
        assert_eq!(copy.project.compound_regions.len(),3);
        assert_eq!(Project::decode(&copy.project.encode().unwrap()).unwrap(),
            copy.project);
    }
}
#[test]
fn source_preservation_from_hand_authored_external_svg_dxf_cad_files(){
    for outer in [
        import_svg(include_str!("fixtures/capsule_external.svg").as_bytes())
            .unwrap().paths.remove(0),
        import_dxf(include_str!("fixtures/capsule_external.dxf").as_bytes())
            .unwrap().paths.remove(0),
    ]{
        let mut e=Editor::default();
        e.apply(Action::ImportPaths{paths:vec![outer]}).unwrap();
        e.apply(Action::AddPolyline{name:"A hole".into(),closed:true,
            points:vec![Point::new(45.0,45.0),Point::new(95.0,45.0),
                Point::new(95.0,75.0),Point::new(45.0,75.0)],
        }).unwrap();
        e.apply(Action::AddPolyline{name:"B boundary".into(),closed:true,
            points:vec![Point::new(50.0,50.0),Point::new(90.0,50.0),
                Point::new(90.0,70.0),Point::new(50.0,70.0)],
        }).unwrap();
        e.apply(Action::AddPolyline{name:"B hole".into(),closed:true,
            points:vec![Point::new(55.0,55.0),Point::new(85.0,55.0),
                Point::new(85.0,65.0),Point::new(55.0,65.0)],
        }).unwrap();
        e.apply(Action::SaveCompoundRegion{ids:vec![1,2],name:"A".into()}).unwrap();
        e.apply(Action::SaveCompoundRegion{ids:vec![3,4],name:"B".into()}).unwrap();
        let old=e.project.clone();
        e.apply(Action::BooleanRegions{
            left_region_id:5,right_region_id:6,
            operation:RegionBoolean::Union,name:"Capsule bool".into(),
        }).unwrap();
        assert_eq!(e.project.paths[4].segments,old.paths[0].segments);
        assert_eq!(e.project.paths[4].nodes,old.paths[0].nodes);
        assert_eq!(e.project.paths.len(),8);
    }
}
