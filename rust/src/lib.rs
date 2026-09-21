mod contact;
mod heightfield;
mod stock_sweep;

use pyo3::prelude::*;
use pyo3::types::PyModule;

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(
        heightfield::rasterize_top_surface,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(contact::compensate_height_field, module)?)?;
    module.add_function(wrap_pyfunction!(stock_sweep::sweep_stock_segment, module)?)?;
    Ok(())
}
