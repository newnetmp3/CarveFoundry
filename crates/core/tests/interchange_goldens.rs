//! R1 CAD-only integration goldens: two hand-authored interchange files
//! and analytical closed-contour offset regressions. No preview samples,
//! CNC cutter compensation, or external desktop application is exercised.
use carvefoundry_core::{
    import_svg,export_svg,import_dxf,export_dxf,
    AnalyticPath,Curve,Point,Project,Stock,polyline,
};
use carvefoundry_core::intersections::validate_simple_analytic_chain;
use carvefoundry_core::mixed_offsets::offset_round_chain;
use carvefoundry_core::topology::offset_exact;

const SVG_CAPSULE:&str=include_str!("fixtures/capsule_external.svg");
const DXF_CAPSULE:&str=include_str!("fixtures/capsule_external.dxf");

fn near(a:Point,b:Point) {
    let gap=(a.x-b.x).hypot(a.y-b.y);
    assert!(gap<0.00001,"World point mismatch: {a:?} vs {b:?} ({gap})");
}
fn world(p:&AnalyticPath,q:Point)->Point{
    q.offset(p.origin.x,p.origin.y)
}
fn assert_same_geometry(a:&AnalyticPath,b:&AnalyticPath){
    assert_eq!(a.closed,b.closed,"closed/open semantics changed");
    assert_eq!(a.nodes.len(),b.nodes.len(),"node count changed");
    assert_eq!(a.segments.len(),b.segments.len(),"edge count changed");
    for (an,bn) in a.nodes.iter().zip(&b.nodes){
        near(world(a,an.position),world(b,bn.position));
    }
    for (sa,sb) in a.segments.iter().zip(&b.segments){
        match (sa.curve,sb.curve){
            (Curve::Line,Curve::Line)=>{},
            (Curve::Arc{center:a_center,clockwise:aw},
             Curve::Arc{center:b_center,clockwise:bw})=>{
                near(world(a,a_center),world(b,b_center));
                assert_eq!(aw,bw,"true arc sweep direction changed");
            },
            (Curve::Cubic{control1:a1,control2:a2},
             Curve::Cubic{control1:b1,control2:b2})=>{
                near(world(a,a1),world(b,b1));
                near(world(a,a2),world(b,b2));
            },
            _=>panic!("CAD primitive changed during interchange")
        }
    }
    a.validate().unwrap();
    b.validate().unwrap();
}
fn project_for(path:AnalyticPath)->Project{
    Project{stock:Stock{width_mm:200.0,height_mm:200.0,thickness_mm:19.0},
        next_id:path.id+1,paths:vec![path],..Project::default()}
}
fn assert_export_import_both(source:&AnalyticPath){
    let project=project_for(source.clone());
    let svg=export_svg(&project).unwrap();
    // SVG true circles stay A instructions; they are NOT visual polylines.
    if source.segments.iter().any(|s|matches!(s.curve,Curve::Arc{..})){
        assert!(svg.contains(" A "),"SVG exporter flattened its true circles");
    }
    let imported=import_svg(svg.as_bytes()).unwrap();
    assert_eq!(imported.paths.len(),1);
    assert_same_geometry(source,&imported.paths[0]);

    let dxf=export_dxf(&project).unwrap();
    assert!(dxf.contains("$INSUNITS\n70\n4"),"DXF must declare millimetres");
    let imported=import_dxf(dxf.as_bytes()).unwrap();
    assert_eq!(imported.units,"mm");
    assert_eq!(imported.paths.len(),1);
    assert_same_geometry(source,&imported.paths[0]);

    // Re-export one interchange form through the other parser twice,
    // checking true centers, source sweep flags and all endpoints.
    let intermediate=project_for(import_svg(svg.as_bytes()).unwrap().paths.remove(0));
    let via_dxf=import_dxf(export_dxf(&intermediate).unwrap().as_bytes()).unwrap();
    assert_same_geometry(source,&via_dxf.paths[0]);
    let intermediate=project_for(import_dxf(dxf.as_bytes()).unwrap().paths.remove(0));
    let via_svg=import_svg(export_svg(&intermediate).unwrap().as_bytes()).unwrap();
    assert_same_geometry(source,&via_svg.paths[0]);
}
fn golden_capsule()->AnalyticPath{
    let imported=import_svg(SVG_CAPSULE.as_bytes()).unwrap();
    assert_eq!(imported.paths.len(),1);
    imported.paths.into_iter().next().unwrap()
}
#[test]
fn hand_authored_external_svg_and_dxf_match_same_exact_capsule(){
    let svg=golden_capsule();
    let dxf=import_dxf(DXF_CAPSULE.as_bytes()).unwrap();
    assert_eq!(dxf.units,"mm");
    assert_eq!(dxf.paths.len(),1);
    assert_same_geometry(&svg,&dxf.paths[0]);
    assert_eq!(svg.nodes.len(),4);
    assert_eq!(svg.segments.len(),4);
    near(svg.nodes[0].position,Point::new(40.0,40.0));
    near(svg.nodes[1].position,Point::new(100.0,40.0));
    near(svg.nodes[2].position,Point::new(100.0,80.0));
    near(svg.nodes[3].position,Point::new(40.0,80.0));
    assert!(matches!(svg.segments[1].curve,
        Curve::Arc{center,clockwise:false} if (center.x-100.0).abs()<1e-7
            && (center.y-60.0).abs()<1e-7));
    assert!(matches!(svg.segments[3].curve,
        Curve::Arc{center,clockwise:false} if (center.x-40.0).abs()<1e-7
            && (center.y-60.0).abs()<1e-7));
    validate_simple_analytic_chain(&svg).unwrap();
    validate_simple_analytic_chain(&dxf.paths[0]).unwrap();
}
#[test]
fn fixture_roundtrips_through_svg_dxf_and_back_without_flattening(){
    let svg=golden_capsule();
    let dxf=import_dxf(DXF_CAPSULE.as_bytes()).unwrap().paths.remove(0);
    assert_export_import_both(&svg);
    assert_export_import_both(&dxf);
}
#[test]
fn offset_capsule_closed_golden_bounds_and_cross_format_roundtrip(){
    let source=golden_capsule();
    for (distance,radius,min_y,max_y) in [
        (3.0,23.0,37.0,83.0),
        (-2.0,18.0,42.0,78.0)
    ]{
        let generated=offset_exact(&source,distance).unwrap();
        assert!(generated.closed);
        assert_eq!(generated.nodes.len(),source.nodes.len());
        assert_eq!(generated.segments,source.segments);
        validate_simple_analytic_chain(&generated).unwrap();
        assert!((generated.nodes[0].position.y-min_y).abs()<1e-7);
        assert!((generated.nodes[2].position.y-max_y).abs()<1e-7);
        if let Curve::Arc{center,..}=generated.segments[1].curve {
            let start=generated.nodes[1].position;
            let actual=(start.x-center.x).hypot(start.y-center.y);
            assert!((actual-radius).abs()<1e-7);
        }else{panic!("Exact offset lost its circle");}
        let rounded=offset_round_chain(&source,distance).unwrap();
        assert_same_geometry(&generated,&rounded);
        assert_export_import_both(&generated);
    }
    assert!(offset_exact(&source,-20.0).is_err(),
        "Collapsed circular radius cannot yield a valid inward offset");
}
#[test]
fn closed_reentrant_straight_profile_accepts_safe_outward_and_inward_offsets(){
    // A hand-authored L-shaped profile: 5 convex vertices and one
    // reentrant corner. Resulting arcs are genuine circles, not samples.
    let source=polyline(1,"Reentrant golden".into(),Point::new(0.0,0.0),
        vec![
            Point::new(10.0,10.0),Point::new(100.0,10.0),
            Point::new(100.0,30.0),Point::new(40.0,30.0),
            Point::new(40.0,90.0),Point::new(10.0,90.0),
        ],true).unwrap();
    validate_simple_analytic_chain(&source).unwrap();
    let initial=source.clone();
    let outer=offset_round_chain(&source,2.0).unwrap();
    let inner=offset_round_chain(&source,-2.0).unwrap();
    assert!(outer.closed&&inner.closed);
    assert_eq!(outer.segments.iter().filter(|s|
        matches!(s.curve,Curve::Arc{..})).count(),5);
    assert_eq!(inner.segments.iter().filter(|s|
        matches!(s.curve,Curve::Arc{..})).count(),1);
    // Miter at the reentrant corner on the outside of the L.
    assert!(outer.nodes.iter().any(|n|
        (n.position.x-42.0).abs()<1e-7&&(n.position.y-32.0).abs()<1e-7));
    validate_simple_analytic_chain(&outer).unwrap();
    validate_simple_analytic_chain(&inner).unwrap();
    assert_eq!(source,initial);
    assert_export_import_both(&outer);
    assert_export_import_both(&inner);
}
#[test]
fn remote_crossing_straight_source_refuses_without_mutation(){
    let source=polyline(1,"Self crossing".into(),Point::new(0.0,0.0),
        vec![Point::new(10.0,10.0),Point::new(70.0,70.0),
            Point::new(10.0,70.0),Point::new(70.0,10.0)],false).unwrap();
    source.validate().unwrap();
    let original=source.clone();
    let err=offset_exact(&source,2.0).unwrap_err();
    assert!(err.contains("cross/touch"),"Unexpected rejection: {err}");
    assert_eq!(source,original);
    assert!(offset_round_chain(&source,2.0).is_err());
}
