use numpy::ndarray::Array2;
use numpy::{IntoPyArray, PyArray2, PyReadonlyArray2};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rayon::prelude::*;

type FootprintSample = (i64, i64, f64);

#[pyfunction]
pub(crate) fn compensate_height_field<'py>(
    py: Python<'py>,
    source_z: PyReadonlyArray2<'py, f64>,
    footprint: Vec<FootprintSample>,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    if footprint.is_empty() {
        return Err(PyValueError::new_err(
            "cutter footprint must contain at least one sample",
        ));
    }
    if footprint
        .iter()
        .any(|(_, _, profile_height)| !profile_height.is_finite())
    {
        return Err(PyValueError::new_err(
            "cutter footprint profile heights must be finite",
        ));
    }

    let source_view = source_z.as_array();
    let height = source_view.nrows();
    let width = source_view.ncols();
    if height == 0 || width == 0 {
        return Err(PyValueError::new_err("source height field cannot be empty"));
    }

    // Detach only after copying Python-owned memory. The numeric kernel itself
    // contains no Python objects and can safely use Rayon worker threads.
    let source: Vec<f64> = source_view.iter().copied().collect();
    let result =
        py.detach(move || compensate_height_field_impl(&source, height, width, &footprint));
    let result = Array2::from_shape_vec((height, width), result)
        .map_err(|error| PyValueError::new_err(error.to_string()))?;

    Ok(result.into_pyarray(py))
}

fn compensate_height_field_impl(
    source: &[f64],
    height: usize,
    width: usize,
    footprint: &[FootprintSample],
) -> Vec<f64> {
    (0..source.len())
        .into_par_iter()
        .map(|destination_index| {
            let destination_y = destination_index / width;
            let destination_x = destination_index % width;
            let mut highest_tip = f64::NEG_INFINITY;
            let mut touched = false;

            for &(offset_y, offset_x, profile_height) in footprint {
                let source_y = destination_y as i64 + offset_y;
                let source_x = destination_x as i64 + offset_x;
                if source_y < 0
                    || source_x < 0
                    || source_y >= height as i64
                    || source_x >= width as i64
                {
                    continue;
                }

                let source_value = source[source_y as usize * width + source_x as usize];
                if !source_value.is_finite() {
                    continue;
                }

                let candidate = source_value - profile_height;
                if candidate > highest_tip {
                    highest_tip = candidate;
                }
                touched = true;
            }

            if touched {
                highest_tip
            } else {
                f64::NAN
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::compensate_height_field_impl;

    #[test]
    fn flat_footprint_uses_local_maximum() {
        let source = [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0];
        let footprint = [
            (0, 0, 0.0),
            (-1, 0, 0.0),
            (1, 0, 0.0),
            (0, -1, 0.0),
            (0, 1, 0.0),
        ];

        let result = compensate_height_field_impl(&source, 3, 3, &footprint);

        assert_eq!(result[4], 1.0);
        assert_eq!(result[1], 1.0);
        assert_eq!(result[3], 1.0);
        assert_eq!(result[0], 0.0);
    }

    #[test]
    fn missing_samples_remain_missing() {
        let source = [f64::NAN; 4];
        let result = compensate_height_field_impl(&source, 2, 2, &[(0, 0, 0.0)]);

        assert!(result.iter().all(|value| value.is_nan()));
    }
}
