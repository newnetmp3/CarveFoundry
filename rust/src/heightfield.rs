use numpy::ndarray::Array2;
use numpy::{IntoPyArray, PyArray2, PyReadonlyArray1, PyReadonlyArray2};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

const BARYCENTRIC_TOLERANCE: f64 = 1.0e-10;

#[pyfunction]
pub(crate) fn rasterize_top_surface<'py>(
    py: Python<'py>,
    vertices: PyReadonlyArray2<'py, f64>,
    faces: PyReadonlyArray2<'py, i64>,
    x_axis: PyReadonlyArray1<'py, f64>,
    y_axis: PyReadonlyArray1<'py, f64>,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let vertex_view = vertices.as_array();
    let face_view = faces.as_array();
    if vertex_view.shape().get(1) != Some(&3) {
        return Err(PyValueError::new_err(
            "vertices must have shape (vertex_count, 3)",
        ));
    }
    if face_view.shape().get(1) != Some(&3) {
        return Err(PyValueError::new_err(
            "faces must have shape (face_count, 3)",
        ));
    }

    // Copy Python-owned buffers once so the expensive kernel can detach from
    // the interpreter. This keeps the PySide event loop responsive while Rust
    // performs CPU-only geometry work.
    let vertex_data: Vec<[f64; 3]> = vertex_view
        .rows()
        .into_iter()
        .map(|row| [row[0], row[1], row[2]])
        .collect();

    let mut face_data = Vec::with_capacity(face_view.nrows());
    for row in face_view.rows() {
        let mut face = [0_usize; 3];
        for corner in 0..3 {
            let index = row[corner];
            if index < 0 || index as usize >= vertex_data.len() {
                return Err(PyValueError::new_err(
                    "faces contains an out-of-range vertex index",
                ));
            }
            face[corner] = index as usize;
        }
        face_data.push(face);
    }

    let x_data: Vec<f64> = x_axis.as_array().iter().copied().collect();
    let y_data: Vec<f64> = y_axis.as_array().iter().copied().collect();
    if x_data.len() < 2 || y_data.len() < 2 {
        return Err(PyValueError::new_err(
            "height-field axes require at least two samples",
        ));
    }

    let x_count = x_data.len();
    let y_count = y_data.len();
    let z_data = py.detach(move || {
        rasterize_top_surface_impl(&vertex_data, &face_data, &x_data, &y_data)
    });
    let z_field = Array2::from_shape_vec((y_count, x_count), z_data)
        .map_err(|error| PyValueError::new_err(error.to_string()))?;

    Ok(z_field.into_pyarray(py))
}

fn rasterize_top_surface_impl(
    vertices: &[[f64; 3]],
    faces: &[[usize; 3]],
    x_axis: &[f64],
    y_axis: &[f64],
) -> Vec<f64> {
    let x_count = x_axis.len();
    let y_count = y_axis.len();
    let mut z_field = vec![f64::NEG_INFINITY; x_count * y_count];

    for face in faces {
        let [x0, y0, z0] = vertices[face[0]];
        let [x1, y1, z1] = vertices[face[1]];
        let [x2, y2, z2] = vertices[face[2]];

        let denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2);
        if denominator.abs() <= BARYCENTRIC_TOLERANCE {
            continue;
        }

        let triangle_min_x = x0.min(x1).min(x2);
        let triangle_max_x = x0.max(x1).max(x2);
        let triangle_min_y = y0.min(y1).min(y2);
        let triangle_max_y = y0.max(y1).max(y2);

        let ix0 = x_axis.partition_point(|value| *value < triangle_min_x);
        let ix1 = x_axis.partition_point(|value| *value <= triangle_max_x);
        let iy0 = y_axis.partition_point(|value| *value < triangle_min_y);
        let iy1 = y_axis.partition_point(|value| *value <= triangle_max_y);
        if ix0 >= ix1 || iy0 >= iy1 {
            continue;
        }

        for (iy, grid_y) in y_axis.iter().enumerate().take(iy1).skip(iy0) {
            for (ix, grid_x) in x_axis.iter().enumerate().take(ix1).skip(ix0) {
                let weight0 =
                    ((y1 - y2) * (*grid_x - x2) + (x2 - x1) * (*grid_y - y2))
                        / denominator;
                let weight1 =
                    ((y2 - y0) * (*grid_x - x2) + (x0 - x2) * (*grid_y - y2))
                        / denominator;
                let weight2 = 1.0 - weight0 - weight1;

                if weight0 < -BARYCENTRIC_TOLERANCE
                    || weight1 < -BARYCENTRIC_TOLERANCE
                    || weight2 < -BARYCENTRIC_TOLERANCE
                {
                    continue;
                }

                let interpolated_z = weight0 * z0 + weight1 * z1 + weight2 * z2;
                let target = &mut z_field[iy * x_count + ix];
                if interpolated_z > *target {
                    *target = interpolated_z;
                }
            }
        }
    }

    z_field
}

#[cfg(test)]
mod tests {
    use super::rasterize_top_surface_impl;

    #[test]
    fn triangle_rasterization_keeps_highest_z() {
        let vertices = [
            [0.0, 0.0, 1.0],
            [2.0, 0.0, 1.0],
            [0.0, 2.0, 1.0],
            [0.0, 0.0, 2.0],
            [2.0, 0.0, 2.0],
            [0.0, 2.0, 2.0],
        ];
        let faces = [[0, 1, 2], [3, 4, 5]];
        let axis = [0.0, 1.0, 2.0];

        let result = rasterize_top_surface_impl(&vertices, &faces, &axis, &axis);

        assert_eq!(result[0], 2.0);
        assert_eq!(result[1], 2.0);
        assert_eq!(result[3], 2.0);
        assert_eq!(result[8], f64::NEG_INFINITY);
    }
}
