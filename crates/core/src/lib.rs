//! CNC-conscious Rust CAD model. No Python, G-code, or controller dependencies.
//! This crate intentionally has NO machine-export implementation.
pub mod geometry;
pub mod project;
pub mod path;
pub mod editor;
pub mod shapes;
pub mod placement;
pub mod interaction;
pub use editor::{Action, Editor};
pub use shapes::{create_shape, polyline, ShapeKind};
pub use placement::{shape_placement, ShapePlacement};
pub use interaction::{pick, movement_delta, nearest_snap, marquee_ids, SnapTarget, SnapKind, Hit, PickMode};
pub use geometry::{Point, polygon_contains};
pub use project::{Contour, Fixture, Project, Stock, MAX_COORD_MM};
pub use path::{AnalyticPath, Curve, PathNode, PathSegment, Primitive};
