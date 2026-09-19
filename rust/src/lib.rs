mod contact;
mod heightfield;

use pyo3::prelude::*;
use pyo3::types::PyModule;

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(heightfield::rasterize_top_surface, module)?)?;
    module.add_function(wrap_pyfunction!(contact::compensate_height_field, module)?)?;
    Ok(())
}
