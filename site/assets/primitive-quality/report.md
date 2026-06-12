# Morphea Primitive Quality Check

- Cases: 8
- Passed: 8
- Failed: 0
- OK: `true`

| Family | Cases | Passed | Failed |
| --- | ---: | ---: | ---: |
| `antialiased_circle` | 1 | 1 | 0 |
| `composition_square_plus_circle` | 1 | 1 | 0 |
| `cutout_horizontal_gap` | 1 | 1 | 0 |
| `filled_circle` | 1 | 1 | 0 |
| `filled_square` | 1 | 1 | 0 |
| `group_parallel_strokes` | 1 | 1 | 0 |
| `horizontal_stroke` | 1 | 1 | 0 |
| `outlined_ring` | 1 | 1 | 0 |

| Case | OK | Actual | L1 | Edge | IoU | Failures |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| `filled_square` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_circle` | `true` | `circle` | 0.00957 | 0.012264 | 0.997963 | n/a |
| `horizontal_stroke` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `outlined_ring` | `true` | `stroke_circle` | 0.053516 | 0.038905 | 0.990867 | n/a |
| `antialiased_circle` | `true` | `circle` | 0.011854 | 0.014403 | 0.947775 | n/a |
| `composition_square_plus_circle_a` | `true` | `rect` | 0.005664 | 0.008035 | 1.0 | n/a |
| `cutout_horizontal_gap_center` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `group_parallel_strokes_horizontal` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
