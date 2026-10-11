//! Persistent, source-exact Boolean parity CAD regions. Test saved
//! membership and design undo; do NOT infer cutter-safe pocket geometry.
use carvefoundry_core::{
    Action,Editor,CompoundRole,Point,Project,
    analyze_compound_paths,import_svg,import_dxf,
};
fn add_box(editor:&mut Editor,id_name:&str,lo:f64,hi:f64) {
    editor.apply(Action::AddPolyline{
        name:id_name.into(),closed:true,
        points:vec![
            Point::new(lo,lo),Point::new(hi,lo),
            Point::new(hi,hi),Point::new(lo,hi),
        ],
    }).unwrap();
}
#[test]
fn legacy_file_stays_loadable_and_compound_membership_roundtrips_with_ids(){
    let mut e=Editor::default();
    add_box(&mut e,"Outside",0.0,100.0);
    add_box(&mut e,"Inside",20.0,40.0);
    let pristine=e.project.clone();
    e.apply(Action::SaveCompoundRegion{
        ids:vec![2,1],name:"Panel with hole".into()}).unwrap();
    assert_eq!(e.project.compound_regions.len(),1);
    assert_eq!(e.project.compound_regions[0].id,3);
    assert_eq!(e.project.compound_regions[0].path_ids,vec![2,1]);
    assert!(e.project.compound_material_at(3,Point::new(10.0,10.0)).unwrap());
    assert!(!e.project.compound_material_at(3,Point::new(30.0,30.0)).unwrap());
    assert!(!e.project.compound_material_at(3,Point::new(120.0,20.0)).unwrap());
    assert!(e.project.compound_material_at(3,Point::new(20.0,30.0))
        .unwrap_err().contains("boundary"));
    let bytes=e.project.encode().unwrap();
    assert_eq!(Project::decode(&bytes).unwrap(),e.project);
    e.apply(Action::RenameCompoundRegion{
        id:3,name:"Revised & label".into()}).unwrap();
    assert_eq!(e.project.compound_regions[0].name,"Revised & label");
    assert!(e.undo());assert_eq!(e.project.compound_regions[0].name,"Panel with hole");
    assert!(e.undo());assert_eq!(e.project,pristine);
    assert!(e.redo());assert_eq!(e.project.compound_regions[0].id,3);
    let json=String::from_utf8(pristine.encode().unwrap()).unwrap();
    assert!(!json.contains("compound_regions"),
        "Older native projects keep their default optional field omitted");
    assert_eq!(Project::decode(json.as_bytes()).unwrap(),pristine);
}
#[test]
fn moving_one_member_preserves_valid_membership_and_bad_edit_is_atomic(){
    let mut e=Editor::default();
    add_box(&mut e,"Outer",0.0,100.0);
    add_box(&mut e,"Hole",20.0,40.0);
    e.apply(Action::SaveCompoundRegion{
        ids:vec![1,2],name:"Panel".into()}).unwrap();
    let initial=e.project.clone();
    e.apply(Action::MovePath{id:2,origin:Point::new(5.0,0.0)}).unwrap();
    assert_eq!(e.project.compound_regions,initial.compound_regions);
    let valid=e.project.clone();
    assert!(e.apply(Action::MovePath{id:2,origin:Point::new(85.0,0.0)}).is_err());
    assert_eq!(e.project,valid,"Failure cannot partially move a hole");
    assert!(e.apply(Action::SetPathClosed{id:2,closed:false}).is_err());
    assert_eq!(e.project,valid,"Failure cannot convert source to open path");
    assert!(e.undo());assert_eq!(e.project,initial);
    assert!(e.redo());assert_eq!(e.project,valid);
    // Drag previews also use Project::validate, so a bad pointer
    // motion returns an error without adopting its candidate.
    e.start_path_drag(2).unwrap();
    assert!(e.preview_path_drag(2,Point::new(95.0,5.0)).is_err());
    assert_eq!(e.project,valid);
    e.cancel_drag();
    assert_eq!(e.project,valid);
}
#[test]
fn removal_and_duplicate_ownership_fail_until_user_removes_saved_region(){
    let mut e=Editor::default();
    add_box(&mut e,"Outer",0.0,100.0);
    add_box(&mut e,"Hole",20.0,40.0);
    e.apply(Action::SaveCompoundRegion{
        ids:vec![1,2],name:"Panel".into()}).unwrap();
    let saved=e.project.clone();
    assert!(e.apply(Action::RemovePath{id:2}).is_err());
    assert_eq!(e.project,saved);
    assert!(e.apply(Action::SaveCompoundRegion{
        ids:vec![2,1],name:"Conflicting".into()}).is_err());
    assert_eq!(e.project,saved);
    assert!(e.apply(Action::RemoveCompoundRegion{id:300}).is_err());
    e.apply(Action::RemoveCompoundRegion{id:3}).unwrap();
    assert!(e.project.compound_regions.is_empty());
    assert_eq!(e.project.paths,saved.paths);
    assert!(e.undo());assert_eq!(e.project,saved);
    assert!(e.redo());
    e.apply(Action::RemovePath{id:2}).unwrap();
    assert_eq!(e.project.paths.len(),1);
}
#[test]
fn nested_island_and_disconnected_outline_evaluate_even_odd_boolean_semantics(){
    let mut e=Editor::default();
    add_box(&mut e,"Outer",0.0,100.0);
    add_box(&mut e,"Hole",20.0,80.0);
    add_box(&mut e,"Island",40.0,60.0);
    e.apply(Action::AddPolyline{
        name:"Separate island".into(),closed:true,
        points:vec![
            Point::new(150.0,150.0),Point::new(190.0,150.0),
            Point::new(190.0,190.0),Point::new(150.0,190.0)
        ]}).unwrap();
    e.apply(Action::SaveCompoundRegion{
        ids:vec![4,2,1,3],name:"Two material domains".into()}).unwrap();
    let id=e.project.compound_regions[0].id;
    assert_eq!(id,5);
    for (point,want) in [
        (Point::new(10.0,10.0),true),
        (Point::new(30.0,30.0),false),
        (Point::new(50.0,50.0),true),
        (Point::new(100.1,50.0),false),
        (Point::new(170.0,170.0),true),
        (Point::new(200.0,200.0),false),
    ]{
        assert_eq!(e.project.compound_material_at(id,point).unwrap(),
            want,"Wrong analytical material at {point:?}");
    }
    let source=e.project.paths.clone();
    let roles=analyze_compound_paths(&source).unwrap();
    assert_eq!(roles.iter().find(|r|r.path_id==2).unwrap().role,CompoundRole::Hole);
    assert_eq!(roles.iter().find(|r|r.path_id==3).unwrap().depth,2);
    assert_eq!(source,e.project.paths);
}
#[test]
fn hand_authored_svg_dxf_circular_capsule_material_with_inner_rectangle(){
    for imported in [
        import_svg(include_str!("fixtures/capsule_external.svg").as_bytes()).unwrap().paths,
        import_dxf(include_str!("fixtures/capsule_external.dxf").as_bytes()).unwrap().paths,
    ]{
        let mut e=Editor::default();
        e.apply(Action::ImportPaths{paths:imported}).unwrap();
        e.apply(Action::AddPolyline{name:"Rectangular hole".into(),closed:true,
            points:vec![
                Point::new(52.0,50.0),Point::new(88.0,50.0),
                Point::new(88.0,70.0),Point::new(52.0,70.0)
            ]}).unwrap();
        e.apply(Action::SaveCompoundRegion{
            ids:vec![1,2],name:"Capsule with hole".into()}).unwrap();
        assert!(e.project.compound_material_at(3,Point::new(110.0,60.0)).unwrap());
        assert!(!e.project.compound_material_at(3,Point::new(60.0,60.0)).unwrap());
        assert!(e.project.compound_material_at(3,Point::new(120.0,60.0)).is_err(),
            "Arc boundary query must explicitly refuse");
        assert_eq!(Project::decode(&e.project.encode().unwrap()).unwrap(),e.project);
    }
}
#[test]
fn malformed_persistent_owners_and_uncertified_curves_fail_closed(){
    let mut e=Editor::default();
    add_box(&mut e,"Outer",0.0,100.0);
    add_box(&mut e,"Hole",20.0,40.0);
    e.apply(Action::SaveCompoundRegion{
        ids:vec![1,2],name:"Panel".into()}).unwrap();
    let mut p=e.project.clone();
    p.compound_regions[0].path_ids.push(999);
    assert!(p.encode().is_err(),"Dangling source IDs must refuse save");
    let mut p=e.project.clone();
    p.compound_regions[0].path_ids.push(1);
    assert!(p.validate().is_err());
    let mut p=e.project.clone();
    p.compound_regions[0].id=1;
    assert!(p.validate().is_err(),"Region IDs must be globally unique");
    let mut p=e.project.clone();
    p.paths[1].origin=Point::new(90.0,0.0);
    let mut bytes=serde_json::to_vec(&p).unwrap();
    assert!(Project::decode(&bytes).is_err(),
        "Tampered .cfd overlapping source geometry must refuse load");
    bytes=serde_json::to_vec(&e.project).unwrap();
    assert_eq!(Project::decode(&bytes).unwrap(),e.project);
    assert!(e.apply(Action::SaveCompoundRegion{
        ids:vec![1,1],name:"Duplicate source".into()}).is_err());
}
