//! CarveFoundry's experimental native 2D layout workspace.
//!
//! A separate Rust front-end during migration. It does not silently replace
//! the mature Python CAM, file format or physical machine preflight.
pub mod arrays;
pub mod geometry;
pub mod nesting;
pub mod multi_sheet;
pub mod svg;
