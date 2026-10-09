//! CNC-conscious Rust CAD model. No Python, G-code, or controller dependencies.
//! This crate intentionally has NO machine-export implementation.
pub mod geometry;
pub mod project;
pub mod path;
pub mod editor;
pub use editor::{Action, Editor};
pub use geometry::{Point, polygon_contains};
pub use project::{Contour, Fixture, Project, Stock, MAX_COORD_MM};
pub use path::{AnalyticPath, Curve, PathNode, PathSegment, Primitive};
