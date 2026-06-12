# Morphea Primitive Quality Check

- Cases: 159
- Passed: 159
- Failed: 0
- OK: `true`

| Family | Cases | Passed | Failed |
| --- | ---: | ---: | ---: |
| `adjacent_different_color_rects` | 3 | 3 | 0 |
| `adjacent_same_color_rects_merge` | 3 | 3 | 0 |
| `adjacent_small_gap_rects` | 3 | 3 | 0 |
| `antialiased_circle` | 3 | 3 | 0 |
| `antialiased_ring` | 3 | 3 | 0 |
| `antialiased_stroke` | 3 | 3 | 0 |
| `composition_circle_plus_stroke` | 3 | 3 | 0 |
| `composition_different_color_separated` | 3 | 3 | 0 |
| `composition_dot_row` | 3 | 3 | 0 |
| `composition_multiple_strokes` | 3 | 3 | 0 |
| `composition_ring_plus_dot` | 3 | 3 | 0 |
| `composition_same_color_separated` | 3 | 3 | 0 |
| `composition_square_plus_circle` | 3 | 3 | 0 |
| `cutout_diagonal_gap` | 3 | 3 | 0 |
| `cutout_horizontal_gap` | 3 | 3 | 0 |
| `diagonal_stroke` | 10 | 10 | 0 |
| `filled_circle` | 10 | 10 | 0 |
| `filled_rectangle` | 10 | 10 | 0 |
| `filled_square` | 10 | 10 | 0 |
| `group_dot_row` | 3 | 3 | 0 |
| `group_parallel_strokes` | 3 | 3 | 0 |
| `group_quad_grid` | 3 | 3 | 0 |
| `horizontal_stroke` | 10 | 10 | 0 |
| `outlined_ring` | 10 | 10 | 0 |
| `overlapping_rectangles_ordered` | 3 | 3 | 0 |
| `palette_drift_primitive` | 3 | 3 | 0 |
| `rounded_rectangle` | 10 | 10 | 0 |
| `simple_quad` | 10 | 10 | 0 |
| `stroke_crossing_rectangle` | 3 | 3 | 0 |
| `touching_circle_stroke` | 3 | 3 | 0 |
| `transparent_circle` | 3 | 3 | 0 |
| `vertical_stroke` | 10 | 10 | 0 |

| Case | OK | Actual | L1 | Edge | IoU | Failures |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| `filled_square` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_small_top_left` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_small_bottom_right` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_medium_left` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_medium_right` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_large_center` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_near_top` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_near_bottom` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_tiny_center` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_offset_center` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_tall` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_wide` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_wide_thick` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_narrow_tall` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_small` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_bottom` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_top_strip` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_right` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_near_square` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `filled_circle` | `true` | `circle` | 0.00957 | 0.012264 | 0.997963 | n/a |
| `filled_circle_small_top_left` | `true` | `circle` | 0.006836 | 0.008881 | 0.977654 | n/a |
| `filled_circle_small_top_right` | `true` | `circle` | 0.008008 | 0.009726 | 0.995373 | n/a |
| `filled_circle_small_bottom_left` | `true` | `circle` | 0.008008 | 0.009726 | 0.995373 | n/a |
| `filled_circle_large_top_right` | `true` | `circle` | 0.012305 | 0.015647 | 0.993377 | n/a |
| `filled_circle_large_bottom_left` | `true` | `circle` | 0.010352 | 0.013955 | 0.993886 | n/a |
| `filled_circle_medium_center` | `true` | `circle` | 0.008398 | 0.010572 | 0.994314 | n/a |
| `filled_circle_large_center` | `true` | `circle` | 0.014648 | 0.017338 | 0.999108 | n/a |
| `filled_circle_near_origin` | `true` | `circle` | 0.00957 | 0.012264 | 0.997963 | n/a |
| `filled_circle_near_corner` | `true` | `circle` | 0.00957 | 0.012264 | 0.997963 | n/a |
| `horizontal_stroke` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `horizontal_stroke_width_1` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `horizontal_stroke_width_2` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `horizontal_stroke_width_3` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `horizontal_stroke_width_5` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `horizontal_stroke_width_6` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `horizontal_stroke_width_8` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `horizontal_stroke_short` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `horizontal_stroke_left` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `horizontal_stroke_right` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke_width_1` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke_width_2` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke_width_3` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke_width_5` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke_width_6` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke_width_8` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke_short` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke_top` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `vertical_stroke_bottom` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `diagonal_stroke` | `true` | `stroke_polyline` | 0.01543 | 0.032139 | 0.958833 | n/a |
| `diagonal_stroke_width_2` | `true` | `stroke_polyline` | 0.016406 | 0.034677 | 0.953934 | n/a |
| `diagonal_stroke_width_3` | `true` | `stroke_polyline` | 0.025977 | 0.035099 | 0.928291 | n/a |
| `diagonal_stroke_width_4` | `true` | `stroke_polyline` | 0.015625 | 0.024527 | 0.93494 | n/a |
| `diagonal_stroke_width_5` | `true` | `stroke_polyline` | 0.000977 | 0.001269 | 0.948608 | n/a |
| `diagonal_stroke_width_6` | `true` | `stroke_polyline` | 0.018945 | 0.020721 | 0.963458 | n/a |
| `diagonal_stroke_width_7` | `true` | `stroke_polyline` | 0.017383 | 0.033408 | 0.963562 | n/a |
| `diagonal_stroke_width_8` | `true` | `stroke_polyline` | 0.007422 | 0.008669 | 0.96861 | n/a |
| `diagonal_stroke_shallow` | `true` | `stroke_polyline` | 0.019531 | 0.029813 | 0.94137 | n/a |
| `diagonal_stroke_steep` | `true` | `stroke_polyline` | 0.013477 | 0.01459 | 0.937547 | n/a |
| `outlined_ring` | `true` | `stroke_circle` | 0.053516 | 0.038905 | 0.990867 | n/a |
| `outlined_ring_thin` | `true` | `stroke_circle` | 0.031641 | 0.031294 | 0.990867 | n/a |
| `outlined_ring_medium` | `true` | `stroke_circle` | 0.064453 | 0.044826 | 0.996568 | n/a |
| `outlined_ring_thick` | `true` | `stroke_circle` | 0.082422 | 0.040597 | 0.996568 | n/a |
| `outlined_ring_large_thick` | `true` | `stroke_circle` | 0.157422 | 0.055821 | 0.99034 | n/a |
| `outlined_ring_small_left` | `true` | `stroke_circle` | 0.053516 | 0.038905 | 0.990867 | n/a |
| `outlined_ring_small_right` | `true` | `stroke_circle` | 0.053516 | 0.038905 | 0.990867 | n/a |
| `outlined_ring_top` | `true` | `stroke_circle` | 0.053516 | 0.038905 | 0.990867 | n/a |
| `outlined_ring_bottom` | `true` | `stroke_circle` | 0.053516 | 0.038905 | 0.990867 | n/a |
| `outlined_ring_large` | `true` | `stroke_circle` | 0.146484 | 0.069353 | 0.991841 | n/a |
| `rounded_rectangle` | `true` | `rounded_rect` | 0.007812 | 0.006343 | 1.0 | n/a |
| `rounded_rectangle_small_radius` | `true` | `rounded_rect` | 0.003906 | 0.004652 | 1.0 | n/a |
| `rounded_rectangle_medium_radius` | `true` | `rounded_rect` | 0.017969 | 0.011418 | 1.0 | n/a |
| `rounded_rectangle_tall` | `true` | `rounded_rect` | 0.013281 | 0.009726 | 1.0 | n/a |
| `rounded_rectangle_wide` | `true` | `rounded_rect` | 0.007812 | 0.006343 | 1.0 | n/a |
| `rounded_rectangle_small` | `true` | `rounded_rect` | 0.004687 | 0.004652 | 1.0 | n/a |
| `rounded_rectangle_bottom` | `true` | `rounded_rect` | 0.009375 | 0.008035 | 1.0 | n/a |
| `rounded_rectangle_top` | `true` | `rounded_rect` | 0.009375 | 0.008035 | 1.0 | n/a |
| `rounded_rectangle_right` | `true` | `rounded_rect` | 0.013281 | 0.009726 | 1.0 | n/a |
| `rounded_rectangle_left` | `true` | `rounded_rect` | 0.013281 | 0.009726 | 1.0 | n/a |
| `simple_quad` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `simple_quad_trapezoid_1` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `simple_quad_trapezoid_2` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `simple_quad_trapezoid_3` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `simple_quad_trapezoid_4` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `simple_quad_trapezoid_5` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `simple_quad_trapezoid_6` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `simple_quad_trapezoid_7` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `simple_quad_trapezoid_8` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `simple_quad_trapezoid_9` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `antialiased_circle` | `true` | `circle` | 0.011854 | 0.014403 | 0.947775 | n/a |
| `antialiased_circle_small` | `true` | `circle` | 0.009327 | 0.011388 | 0.918098 | n/a |
| `antialiased_circle_large` | `true` | `circle` | 0.019969 | 0.024665 | 0.966325 | n/a |
| `antialiased_ring` | `true` | `stroke_circle` | 0.057211 | 0.03744 | 0.946301 | n/a |
| `antialiased_ring_medium` | `true` | `stroke_circle` | 0.075009 | 0.049032 | 0.959586 | n/a |
| `antialiased_ring_large` | `true` | `stroke_circle` | 0.130934 | 0.062376 | 0.965777 | n/a |
| `antialiased_stroke_horizontal` | `true` | `stroke_polyline` | 0.006 | 0.006652 | 0.764454 | n/a |
| `antialiased_stroke_vertical` | `true` | `stroke_polyline` | 0.006048 | 0.006211 | 0.981132 | n/a |
| `antialiased_stroke_diagonal` | `true` | `stroke_polyline` | 0.020594 | 0.030997 | 0.9742 | n/a |
| `palette_drift_square` | `true` | `rect` | 1.5e-05 | 3.2e-05 | 1.0 | n/a |
| `palette_drift_rectangle` | `true` | `rect` | 1.8e-05 | 3.6e-05 | 1.0 | n/a |
| `palette_drift_circle` | `true` | `circle` | 0.009585 | 0.012295 | 0.997963 | n/a |
| `transparent_circle` | `true` | `circle` | 0.00957 | 0.012264 | 0.997963 | n/a |
| `transparent_circle_small` | `true` | `circle` | 0.008008 | 0.009726 | 0.995373 | n/a |
| `transparent_circle_offset` | `true` | `circle` | 0.009961 | 0.011418 | 0.994443 | n/a |
| `composition_same_color_two_squares` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `composition_same_color_square_circle` | `true` | `rect` | 0.005664 | 0.008035 | 1.0 | n/a |
| `composition_same_color_rect_circle` | `true` | `rect` | 0.005273 | 0.007189 | 1.0 | n/a |
| `composition_different_color_square_circle` | `true` | `rect` | 0.004405 | 0.006233 | 1.0 | n/a |
| `composition_different_color_two_rects` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `composition_different_color_circle_rect` | `true` | `circle` | 0.005317 | 0.006889 | 0.977654 | n/a |
| `composition_circle_plus_horizontal_stroke` | `true` | `circle` | 0.006836 | 0.008881 | 0.977654 | n/a |
| `composition_circle_plus_vertical_stroke` | `true` | `circle` | 0.006836 | 0.008881 | 0.977654 | n/a |
| `composition_circle_plus_diagonal_stroke` | `true` | `circle` | 0.010156 | 0.017127 | 0.986705 | n/a |
| `composition_square_plus_circle_a` | `true` | `rect` | 0.005664 | 0.008035 | 1.0 | n/a |
| `composition_square_plus_circle_b` | `true` | `rect` | 0.005664 | 0.008035 | 1.0 | n/a |
| `composition_square_plus_circle_c` | `true` | `rect` | 0.005664 | 0.008035 | 1.0 | n/a |
| `composition_ring_plus_dot_a` | `true` | `stroke_circle` | 0.054102 | 0.040174 | 0.976228 | n/a |
| `composition_ring_plus_dot_b` | `true` | `stroke_circle` | 0.054102 | 0.040174 | 0.976228 | n/a |
| `composition_ring_plus_dot_c` | `true` | `stroke_circle` | 0.054102 | 0.040174 | 0.976228 | n/a |
| `composition_dot_row_three` | `true` | `circle` | 0.007617 | 0.011418 | 0.979167 | n/a |
| `composition_dot_row_four` | `true` | `circle` | 0.010156 | 0.015224 | 0.979167 | n/a |
| `composition_dot_column_three` | `true` | `circle` | 0.007617 | 0.011418 | 0.979167 | n/a |
| `composition_multiple_horizontal_strokes` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `composition_multiple_vertical_strokes` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `composition_multiple_mixed_strokes` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_different_color_rects_horizontal` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_different_color_rects_vertical` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_different_color_rects_offset` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_same_color_rects_merge_horizontal` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_same_color_rects_merge_vertical` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_same_color_rects_merge_wide` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_small_gap_rects_horizontal` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_small_gap_rects_vertical` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_small_gap_rects_offset` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `touching_circle_stroke_right` | `true` | `circle` | 0.00918 | 0.011206 | 0.983268 | n/a |
| `touching_circle_stroke_left` | `true` | `circle` | 0.004102 | 0.005662 | 0.983268 | n/a |
| `touching_circle_stroke_bottom` | `true` | `circle` | 0.00918 | 0.011206 | 0.983268 | n/a |
| `stroke_crossing_rectangle_horizontal` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `stroke_crossing_rectangle_vertical` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `stroke_crossing_rectangle_low` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `overlapping_rectangles_bottom_right` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `overlapping_rectangles_top_left` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `overlapping_rectangles_side` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `cutout_horizontal_gap_center` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `cutout_horizontal_gap_top` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `cutout_horizontal_gap_bottom` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `cutout_diagonal_gap_down` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `cutout_diagonal_gap_up` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `cutout_diagonal_gap_short` | `true` | `rect` | 0.0 | 0.0 | 1.0 | n/a |
| `group_parallel_strokes_horizontal` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `group_parallel_strokes_vertical` | `true` | `stroke_polyline` | 0.0 | 0.0 | 1.0 | n/a |
| `group_parallel_strokes_diagonal` | `true` | `stroke_polyline` | 0.005273 | 0.010784 | 0.941348 | n/a |
| `group_dot_row_three` | `true` | `circle` | 0.007617 | 0.011418 | 0.979167 | n/a |
| `group_dot_row_four` | `true` | `circle` | 0.010156 | 0.015224 | 0.979167 | n/a |
| `group_dot_column_three` | `true` | `circle` | 0.007617 | 0.011418 | 0.979167 | n/a |
| `group_quad_grid_row` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `group_quad_grid_two_by_two` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
| `group_quad_grid_column` | `true` | `quad` | 0.0 | 0.0 | 1.0 | n/a |
