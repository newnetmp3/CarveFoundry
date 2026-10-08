//! CarveFoundry's experimental native 2D layout workspace.
//!
//! A separate Rust front-end during migration. It does not silently replace
//! the mature Python CAM, file format or physical machine preflight.
pub mod arrays;
pub mod cam_readout;
pub mod geometry;
pub mod inlay;
pub mod nesting;
pub mod multi_sheet;
pub mod plan_io;
pub mod precision;
pub mod svg;
pub mod source_placement;
