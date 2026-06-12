# Morphea Primitive Quality Check

- Cases: 291
- Passed: 291
- Failed: 0
- OK: `true`

| Family | Cases | Passed | Failed |
| --- | ---: | ---: | ---: |
| `adjacent_different_color_rects` | 3 | 3 | 0 |
| `adjacent_same_color_rects_merge` | 3 | 3 | 0 |
| `adjacent_small_gap_rects` | 3 | 3 | 0 |
| `antialiased_arc` | 3 | 3 | 0 |
| `antialiased_circle` | 3 | 3 | 0 |
| `antialiased_curve` | 3 | 3 | 0 |
| `antialiased_ellipse` | 3 | 3 | 0 |
| `antialiased_ring` | 3 | 3 | 0 |
| `antialiased_stroke` | 3 | 3 | 0 |
| `arc_down` | 3 | 3 | 0 |
| `arc_left` | 3 | 3 | 0 |
| `arc_right` | 3 | 3 | 0 |
| `arc_shallow` | 3 | 3 | 0 |
| `arc_small_radius` | 3 | 3 | 0 |
| `arc_steep` | 3 | 3 | 0 |
| `arc_thick` | 3 | 3 | 0 |
| `arc_up` | 3 | 3 | 0 |
| `composition_arc_circle` | 3 | 3 | 0 |
| `composition_arc_rect` | 3 | 3 | 0 |
| `composition_circle_plus_stroke` | 3 | 3 | 0 |
| `composition_curve_crossing_rect` | 3 | 3 | 0 |
| `composition_curve_group` | 3 | 3 | 0 |
| `composition_curve_touching_circle` | 3 | 3 | 0 |
| `composition_different_color_separated` | 3 | 3 | 0 |
| `composition_dot_row` | 3 | 3 | 0 |
| `composition_ellipse_stroke` | 3 | 3 | 0 |
| `composition_multiple_strokes` | 3 | 3 | 0 |
| `composition_parallel_arcs` | 3 | 3 | 0 |
| `composition_ring_plus_dot` | 3 | 3 | 0 |
| `composition_same_color_separated` | 3 | 3 | 0 |
| `composition_square_plus_circle` | 3 | 3 | 0 |
| `curve_asymmetric` | 3 | 3 | 0 |
| `curve_diagonal` | 3 | 3 | 0 |
| `curve_quadratic` | 3 | 3 | 0 |
| `curve_round_caps` | 3 | 3 | 0 |
| `curve_s` | 3 | 3 | 0 |
| `curve_square_caps` | 3 | 3 | 0 |
| `curve_wave` | 3 | 3 | 0 |
| `cutout_curve_circle` | 3 | 3 | 0 |
| `cutout_curve_crossing` | 3 | 3 | 0 |
| `cutout_curve_rect` | 3 | 3 | 0 |
| `cutout_curve_ring` | 3 | 3 | 0 |
| `cutout_diagonal_gap` | 3 | 3 | 0 |
| `cutout_horizontal_gap` | 3 | 3 | 0 |
| `cutout_near_background` | 3 | 3 | 0 |
| `diagonal_stroke` | 10 | 10 | 0 |
| `drift_curve` | 3 | 3 | 0 |
| `ellipse_horizontal` | 3 | 3 | 0 |
| `ellipse_large` | 3 | 3 | 0 |
| `ellipse_small` | 3 | 3 | 0 |
| `ellipse_vertical` | 3 | 3 | 0 |
| `ellipse_wide` | 3 | 3 | 0 |
| `filled_circle` | 10 | 10 | 0 |
| `filled_rectangle` | 10 | 10 | 0 |
| `filled_square` | 10 | 10 | 0 |
| `group_dot_row` | 3 | 3 | 0 |
| `group_parallel_strokes` | 3 | 3 | 0 |
| `group_quad_grid` | 3 | 3 | 0 |
| `horizontal_stroke` | 10 | 10 | 0 |
| `organic_asymmetric` | 3 | 3 | 0 |
| `organic_blob` | 3 | 3 | 0 |
| `organic_compound` | 3 | 3 | 0 |
| `organic_crescent` | 3 | 3 | 0 |
| `organic_leaf` | 3 | 3 | 0 |
| `outlined_ring` | 10 | 10 | 0 |
| `overlapping_rectangles_ordered` | 3 | 3 | 0 |
| `palette_drift_primitive` | 3 | 3 | 0 |
| `rounded_rectangle` | 10 | 10 | 0 |
| `simple_quad` | 10 | 10 | 0 |
| `stroke_crossing_rectangle` | 3 | 3 | 0 |
| `stroked_ellipse` | 3 | 3 | 0 |
| `touching_circle_stroke` | 3 | 3 | 0 |
| `transparent_arc` | 3 | 3 | 0 |
| `transparent_circle` | 3 | 3 | 0 |
| `transparent_curve` | 3 | 3 | 0 |
| `vertical_stroke` | 10 | 10 | 0 |

| Case | OK | Actual | L1 | Edge | SVG L1 | SVG Edge | IoU | Failures |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `filled_square` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_small_top_left` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_small_bottom_right` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_medium_left` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_medium_right` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_large_center` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_near_top` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_near_bottom` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_tiny_center` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_square_offset_center` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_tall` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_wide` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_wide_thick` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_narrow_tall` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_small` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_bottom` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_top_strip` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_right` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_rectangle_near_square` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `filled_circle` | `true` | `circle` | 0.0 | 0.0 | 0.010459 | 0.012772 | 1.0 | n/a |
| `filled_circle_small_top_left` | `true` | `circle` | 0.0 | 0.0 | 0.007918 | 0.009677 | 1.0 | n/a |
| `filled_circle_small_top_right` | `true` | `circle` | 0.0 | 0.0 | 0.008164 | 0.010311 | 1.0 | n/a |
| `filled_circle_small_bottom_left` | `true` | `circle` | 0.0 | 0.0 | 0.008164 | 0.010311 | 1.0 | n/a |
| `filled_circle_large_top_right` | `true` | `circle` | 0.0 | 0.0 | 0.013557 | 0.016805 | 1.0 | n/a |
| `filled_circle_large_bottom_left` | `true` | `circle` | 0.0 | 0.0 | 0.011216 | 0.014036 | 1.0 | n/a |
| `filled_circle_medium_center` | `true` | `circle` | 0.0 | 0.0 | 0.008945 | 0.010916 | 1.0 | n/a |
| `filled_circle_large_center` | `true` | `circle` | 0.0 | 0.0 | 0.014514 | 0.017949 | 1.0 | n/a |
| `filled_circle_near_origin` | `true` | `circle` | 0.0 | 0.0 | 0.010459 | 0.012772 | 1.0 | n/a |
| `filled_circle_near_corner` | `true` | `circle` | 0.0 | 0.0 | 0.010459 | 0.012772 | 1.0 | n/a |
| `horizontal_stroke` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.004517 | 0.004995 | 1.0 | n/a |
| `horizontal_stroke_width_1` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.004859 | 0.00538 | 1.0 | n/a |
| `horizontal_stroke_width_2` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.005005 | 0.005524 | 1.0 | n/a |
| `horizontal_stroke_width_3` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.004761 | 0.005259 | 1.0 | n/a |
| `horizontal_stroke_width_5` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.005444 | 0.005998 | 1.0 | n/a |
| `horizontal_stroke_width_6` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.00481 | 0.005311 | 1.0 | n/a |
| `horizontal_stroke_width_8` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.005493 | 0.00605 | 1.0 | n/a |
| `horizontal_stroke_short` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.002954 | 0.003303 | 1.0 | n/a |
| `horizontal_stroke_left` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.00354 | 0.003937 | 1.0 | n/a |
| `horizontal_stroke_right` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.00354 | 0.003937 | 1.0 | n/a |
| `vertical_stroke` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.004516 | 0.004995 | 1.0 | n/a |
| `vertical_stroke_width_1` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.004858 | 0.00538 | 1.0 | n/a |
| `vertical_stroke_width_2` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.005005 | 0.005524 | 1.0 | n/a |
| `vertical_stroke_width_3` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.004761 | 0.005259 | 1.0 | n/a |
| `vertical_stroke_width_5` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.005444 | 0.005998 | 1.0 | n/a |
| `vertical_stroke_width_6` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.004809 | 0.005311 | 1.0 | n/a |
| `vertical_stroke_width_8` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.005493 | 0.00605 | 1.0 | n/a |
| `vertical_stroke_short` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.002954 | 0.003303 | 1.0 | n/a |
| `vertical_stroke_top` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.00354 | 0.003937 | 1.0 | n/a |
| `vertical_stroke_bottom` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.00354 | 0.003937 | 1.0 | n/a |
| `diagonal_stroke` | `true` | `stroke_polyline` | 0.01543 | 0.032139 | 0.011036 | 0.022545 | 0.969961 | n/a |
| `diagonal_stroke_width_2` | `true` | `stroke_polyline` | 0.016406 | 0.034677 | 0.012085 | 0.022674 | 0.953261 | n/a |
| `diagonal_stroke_width_3` | `true` | `stroke_polyline` | 0.025977 | 0.035099 | 0.017196 | 0.024141 | 0.944861 | n/a |
| `diagonal_stroke_width_4` | `true` | `stroke_polyline` | 0.015625 | 0.024527 | 0.018164 | 0.023708 | 0.946783 | n/a |
| `diagonal_stroke_width_5` | `true` | `stroke_polyline` | 0.000977 | 0.001269 | 0.004699 | 0.005695 | 0.962305 | n/a |
| `diagonal_stroke_width_6` | `true` | `stroke_polyline` | 0.018945 | 0.020721 | 0.014703 | 0.030009 | 0.962374 | n/a |
| `diagonal_stroke_width_7` | `true` | `stroke_polyline` | 0.017383 | 0.033408 | 0.016792 | 0.023816 | 0.966573 | n/a |
| `diagonal_stroke_width_8` | `true` | `stroke_polyline` | 0.007422 | 0.008669 | 0.010534 | 0.012574 | 0.966217 | n/a |
| `diagonal_stroke_shallow` | `true` | `stroke_polyline` | 0.019531 | 0.029813 | 0.016332 | 0.02078 | 0.940362 | n/a |
| `diagonal_stroke_steep` | `true` | `stroke_polyline` | 0.013477 | 0.01459 | 0.013411 | 0.017542 | 0.937168 | n/a |
| `outlined_ring` | `true` | `stroke_circle` | 0.016797 | 0.021144 | 0.017276 | 0.021368 | 0.990867 | n/a |
| `outlined_ring_thin` | `true` | `stroke_circle` | 0.01875 | 0.022836 | 0.019324 | 0.023405 | 0.990867 | n/a |
| `outlined_ring_medium` | `true` | `stroke_circle` | 0.021484 | 0.024527 | 0.021053 | 0.025385 | 0.996568 | n/a |
| `outlined_ring_thick` | `true` | `stroke_circle` | 0.019531 | 0.022836 | 0.019005 | 0.023348 | 0.996568 | n/a |
| `outlined_ring_large_thick` | `true` | `stroke_circle` | 0.026562 | 0.031294 | 0.025908 | 0.03152 | 0.99034 | n/a |
| `outlined_ring_small_left` | `true` | `stroke_circle` | 0.016797 | 0.021144 | 0.017276 | 0.021368 | 0.990867 | n/a |
| `outlined_ring_small_right` | `true` | `stroke_circle` | 0.016797 | 0.021144 | 0.017276 | 0.021368 | 0.990867 | n/a |
| `outlined_ring_top` | `true` | `stroke_circle` | 0.016797 | 0.021144 | 0.017276 | 0.021368 | 0.990867 | n/a |
| `outlined_ring_bottom` | `true` | `stroke_circle` | 0.016797 | 0.021144 | 0.017276 | 0.021368 | 0.990867 | n/a |
| `outlined_ring_large` | `true` | `stroke_circle` | 0.031641 | 0.037214 | 0.030744 | 0.037564 | 0.991841 | n/a |
| `rounded_rectangle` | `true` | `rounded_rect` | 0.00926 | 0.009346 | 0.006287 | 0.007185 | 0.931713 | n/a |
| `rounded_rectangle_small_radius` | `true` | `rounded_rect` | 0.005992 | 0.006592 | 0.00516 | 0.005886 | 0.922727 | n/a |
| `rounded_rectangle_medium_radius` | `true` | `rounded_rect` | 0.019439 | 0.014818 | 0.01096 | 0.012272 | 0.94237 | n/a |
| `rounded_rectangle_tall` | `true` | `rounded_rect` | 0.014808 | 0.013096 | 0.010333 | 0.011333 | 0.946528 | n/a |
| `rounded_rectangle_wide` | `true` | `rounded_rect` | 0.010141 | 0.010255 | 0.007168 | 0.008094 | 0.926282 | n/a |
| `rounded_rectangle_small` | `true` | `rounded_rect` | 0.00629 | 0.0067 | 0.004631 | 0.0053 | 0.905093 | n/a |
| `rounded_rectangle_bottom` | `true` | `rounded_rect` | 0.010972 | 0.010295 | 0.007988 | 0.008971 | 0.929426 | n/a |
| `rounded_rectangle_top` | `true` | `rounded_rect` | 0.010972 | 0.010295 | 0.007988 | 0.008971 | 0.929426 | n/a |
| `rounded_rectangle_right` | `true` | `rounded_rect` | 0.013575 | 0.011823 | 0.0091 | 0.01006 | 0.9375 | n/a |
| `rounded_rectangle_left` | `true` | `rounded_rect` | 0.013575 | 0.011823 | 0.0091 | 0.01006 | 0.9375 | n/a |
| `simple_quad` | `true` | `quad` | 0.0 | 0.0 | 0.010978 | 0.012798 | 1.0 | n/a |
| `simple_quad_trapezoid_1` | `true` | `quad` | 0.0 | 0.0 | 0.010735 | 0.012366 | 1.0 | n/a |
| `simple_quad_trapezoid_2` | `true` | `quad` | 0.0 | 0.0 | 0.012979 | 0.014669 | 1.0 | n/a |
| `simple_quad_trapezoid_3` | `true` | `quad` | 0.0 | 0.0 | 0.013276 | 0.015222 | 1.0 | n/a |
| `simple_quad_trapezoid_4` | `true` | `quad` | 0.0 | 0.0 | 0.010638 | 0.01189 | 1.0 | n/a |
| `simple_quad_trapezoid_5` | `true` | `quad` | 0.0 | 0.0 | 0.012589 | 0.014714 | 1.0 | n/a |
| `simple_quad_trapezoid_6` | `true` | `quad` | 0.0 | 0.0 | 0.009469 | 0.010725 | 1.0 | n/a |
| `simple_quad_trapezoid_7` | `true` | `quad` | 0.0 | 0.0 | 0.012296 | 0.014348 | 1.0 | n/a |
| `simple_quad_trapezoid_8` | `true` | `quad` | 0.0 | 0.0 | 0.012294 | 0.014605 | 1.0 | n/a |
| `simple_quad_trapezoid_9` | `true` | `quad` | 0.0 | 0.0 | 0.010299 | 0.011676 | 1.0 | n/a |
| `arc_up` | `true` | `arc` | 0.008789 | 0.012475 | 0.011243 | 0.013892 | 0.834573 | n/a |
| `arc_up_small` | `true` | `arc` | 0.008398 | 0.010995 | 0.010353 | 0.012904 | 0.817409 | n/a |
| `arc_up_large` | `true` | `arc` | 0.008984 | 0.012898 | 0.012188 | 0.015151 | 0.879785 | n/a |
| `arc_down` | `true` | `arc` | 0.011523 | 0.014801 | 0.01182 | 0.014251 | 0.812863 | n/a |
| `arc_down_small` | `true` | `arc` | 0.009375 | 0.011418 | 0.010215 | 0.012132 | 0.787507 | n/a |
| `arc_down_large` | `true` | `arc` | 0.013086 | 0.016704 | 0.013276 | 0.015895 | 0.811033 | n/a |
| `arc_left` | `true` | `arc` | 0.00957 | 0.012898 | 0.010728 | 0.013501 | 0.844136 | n/a |
| `arc_left_small` | `true` | `arc` | 0.007617 | 0.010784 | 0.009484 | 0.01216 | 0.847364 | n/a |
| `arc_left_large` | `true` | `arc` | 0.009766 | 0.014378 | 0.011642 | 0.014416 | 0.865535 | n/a |
| `arc_right` | `true` | `arc` | 0.011523 | 0.014801 | 0.011945 | 0.014401 | 0.812863 | n/a |
| `arc_right_small` | `true` | `arc` | 0.009375 | 0.011418 | 0.010326 | 0.012237 | 0.787507 | n/a |
| `arc_right_large` | `true` | `arc` | 0.011328 | 0.014378 | 0.012763 | 0.015135 | 0.812874 | n/a |
| `arc_shallow` | `true` | `arc` | 0.007227 | 0.008669 | 0.009241 | 0.010431 | 0.814639 | n/a |
| `arc_shallow_small` | `true` | `arc` | 0.007227 | 0.008458 | 0.008353 | 0.009544 | 0.74179 | n/a |
| `arc_shallow_large` | `true` | `arc` | 0.008203 | 0.010149 | 0.009596 | 0.011049 | 0.874591 | n/a |
| `arc_steep` | `true` | `arc` | 0.010937 | 0.014801 | 0.012098 | 0.015006 | 0.89106 | n/a |
| `arc_steep_small` | `true` | `arc` | 0.010742 | 0.013744 | 0.01161 | 0.014417 | 0.867325 | n/a |
| `arc_steep_large` | `true` | `arc` | 0.011523 | 0.01607 | 0.01223 | 0.015283 | 0.901281 | n/a |
| `arc_thick` | `true` | `arc` | 0.010352 | 0.013744 | 0.0147 | 0.016849 | 0.850367 | n/a |
| `arc_thick_medium` | `true` | `arc` | 0.010937 | 0.013532 | 0.011985 | 0.013807 | 0.821931 | n/a |
| `arc_thick_wide` | `true` | `arc` | 0.014453 | 0.019453 | 0.015262 | 0.018793 | 0.89302 | n/a |
| `arc_small_radius` | `true` | `arc` | 0.005469 | 0.007189 | 0.007432 | 0.00894 | 0.781582 | n/a |
| `arc_small_radius_left` | `true` | `arc` | 0.005664 | 0.007612 | 0.006663 | 0.008407 | 0.789112 | n/a |
| `arc_small_radius_right` | `true` | `arc` | 0.006641 | 0.008881 | 0.008055 | 0.009986 | 0.828327 | n/a |
| `curve_quadratic` | `true` | `stroke_path` | 0.014258 | 0.018184 | 0.015958 | 0.018813 | 0.903722 | n/a |
| `curve_quadratic_narrow` | `true` | `stroke_path` | 0.011523 | 0.014378 | 0.015166 | 0.017167 | 0.89553 | n/a |
| `curve_quadratic_offset` | `true` | `stroke_path` | 0.014648 | 0.019453 | 0.015275 | 0.017724 | 0.901029 | n/a |
| `curve_s` | `true` | `stroke_path` | 0.017578 | 0.023259 | 0.018812 | 0.022186 | 0.891118 | n/a |
| `curve_s_mirrored` | `true` | `stroke_path` | 0.013867 | 0.015647 | 0.014788 | 0.015519 | 0.891348 | n/a |
| `curve_s_tight` | `true` | `stroke_path` | 0.016406 | 0.02347 | 0.019132 | 0.023542 | 0.890172 | n/a |
| `curve_wave` | `true` | `stroke_path` | 0.014258 | 0.017338 | 0.014188 | 0.015868 | 0.820741 | n/a |
| `curve_wave_inverted` | `true` | `stroke_path` | 0.010352 | 0.013955 | 0.011507 | 0.013962 | 0.839172 | n/a |
| `curve_wave_offset` | `true` | `stroke_path` | 0.012695 | 0.014801 | 0.01398 | 0.015388 | 0.878671 | n/a |
| `curve_asymmetric` | `true` | `stroke_path` | 0.01582 | 0.020087 | 0.017309 | 0.019148 | 0.88065 | n/a |
| `curve_asymmetric_right` | `true` | `stroke_path` | 0.016797 | 0.021144 | 0.01549 | 0.017817 | 0.880107 | n/a |
| `curve_asymmetric_low` | `true` | `stroke_path` | 0.014063 | 0.016915 | 0.015824 | 0.017299 | 0.90341 | n/a |
| `curve_diagonal` | `true` | `stroke_path` | 0.018164 | 0.031082 | 0.020571 | 0.030118 | 0.903236 | n/a |
| `curve_diagonal_up` | `true` | `stroke_path` | 0.008398 | 0.008458 | 0.011174 | 0.011451 | 0.894332 | n/a |
| `curve_diagonal_steep` | `true` | `stroke_path` | 0.020117 | 0.034042 | 0.02194 | 0.031785 | 0.912622 | n/a |
| `curve_square_caps` | `true` | `stroke_path` | 0.012891 | 0.022201 | 0.018516 | 0.024846 | 0.952772 | n/a |
| `curve_square_caps_down` | `true` | `stroke_path` | 0.008008 | 0.008881 | 0.011828 | 0.012441 | 0.951546 | n/a |
| `curve_square_caps_long` | `true` | `stroke_path` | 0.013477 | 0.024527 | 0.015205 | 0.021534 | 0.951839 | n/a |
| `curve_round_caps` | `true` | `stroke_path` | 0.01875 | 0.030025 | 0.018112 | 0.024546 | 0.914922 | n/a |
| `curve_round_caps_down` | `true` | `stroke_path` | 0.00918 | 0.009726 | 0.011086 | 0.01179 | 0.906686 | n/a |
| `curve_round_caps_long` | `true` | `stroke_path` | 0.014453 | 0.023682 | 0.0175 | 0.023633 | 0.913121 | n/a |
| `ellipse_horizontal` | `true` | `ellipse` | 0.012305 | 0.014801 | 0.010498 | 0.013365 | 0.938667 | n/a |
| `ellipse_horizontal_flat` | `true` | `ellipse` | 0.012305 | 0.014801 | 0.01084 | 0.013483 | 0.932945 | n/a |
| `ellipse_horizontal_tall` | `true` | `ellipse` | 0.011914 | 0.014801 | 0.010692 | 0.013627 | 0.941968 | n/a |
| `ellipse_vertical` | `true` | `ellipse` | 0.012305 | 0.014801 | 0.010498 | 0.013365 | 0.938667 | n/a |
| `ellipse_vertical_narrow` | `true` | `ellipse` | 0.012305 | 0.014801 | 0.01084 | 0.013483 | 0.932945 | n/a |
| `ellipse_vertical_wide` | `true` | `ellipse` | 0.011914 | 0.014801 | 0.010692 | 0.013628 | 0.941968 | n/a |
| `ellipse_small` | `true` | `ellipse` | 0.006055 | 0.007189 | 0.00515 | 0.006437 | 0.879121 | n/a |
| `ellipse_small_top_left` | `true` | `ellipse` | 0.006055 | 0.007189 | 0.00515 | 0.006437 | 0.879121 | n/a |
| `ellipse_small_bottom_right` | `true` | `ellipse` | 0.006055 | 0.007189 | 0.00515 | 0.006437 | 0.879121 | n/a |
| `ellipse_large` | `true` | `ellipse` | 0.018164 | 0.020721 | 0.014815 | 0.018983 | 0.958494 | n/a |
| `ellipse_large_tall` | `true` | `ellipse` | 0.016992 | 0.021567 | 0.015428 | 0.019706 | 0.960624 | n/a |
| `ellipse_large_low` | `true` | `ellipse` | 0.016602 | 0.020721 | 0.014722 | 0.018698 | 0.957844 | n/a |
| `ellipse_wide` | `true` | `ellipse` | 0.010742 | 0.013955 | 0.011012 | 0.012742 | 0.90566 | n/a |
| `ellipse_wide_thin` | `true` | `ellipse` | 0.010742 | 0.013109 | 0.010132 | 0.011845 | 0.904239 | n/a |
| `ellipse_wide_thick` | `true` | `ellipse` | 0.012695 | 0.015647 | 0.011964 | 0.014366 | 0.924665 | n/a |
| `stroked_ellipse` | `true` | `stroke_ellipse` | 0.030859 | 0.033408 | 0.028364 | 0.030679 | 0.925291 | n/a |
| `stroked_ellipse_thin` | `true` | `stroke_ellipse` | 0.022266 | 0.027065 | 0.020282 | 0.02552 | 0.971134 | n/a |
| `stroked_ellipse_thick` | `true` | `stroke_ellipse` | 0.035937 | 0.039328 | 0.030681 | 0.034044 | 0.948849 | n/a |
| `antialiased_ellipse` | `true` | `ellipse` | 0.014877 | 0.017675 | 0.013182 | 0.013746 | 0.938059 | n/a |
| `antialiased_ellipse_narrow` | `true` | `ellipse` | 0.012237 | 0.014518 | 0.010824 | 0.011585 | 0.925777 | n/a |
| `antialiased_ellipse_vertical` | `true` | `ellipse` | 0.013703 | 0.016587 | 0.012282 | 0.012966 | 0.935972 | n/a |
| `antialiased_arc` | `true` | `arc` | 0.012235 | 0.014908 | 0.01351 | 0.013921 | 0.805054 | n/a |
| `antialiased_arc_steep` | `true` | `arc` | 0.013844 | 0.016588 | 0.013359 | 0.013719 | 0.868194 | n/a |
| `antialiased_arc_thick` | `true` | `arc` | 0.012888 | 0.015515 | 0.014558 | 0.014993 | 0.879498 | n/a |
| `antialiased_curve_s` | `true` | `stroke_path` | 0.018818 | 0.024752 | 0.01687 | 0.018547 | 0.8968 | n/a |
| `antialiased_curve_wave` | `true` | `stroke_path` | 0.017426 | 0.01936 | 0.012204 | 0.011989 | 0.846439 | n/a |
| `antialiased_curve_quadratic` | `true` | `stroke_path` | 0.02142 | 0.024024 | 0.017905 | 0.018189 | 0.89317 | n/a |
| `drift_curve_s` | `true` | `stroke_path` | 0.017593 | 0.023283 | 0.018814 | 0.022171 | 0.891118 | n/a |
| `drift_curve_quadratic` | `true` | `stroke_path` | 0.014271 | 0.018198 | 0.015957 | 0.018804 | 0.903722 | n/a |
| `drift_curve_wave` | `true` | `stroke_path` | 0.014832 | 0.018579 | 0.014762 | 0.017109 | 0.820741 | n/a |
| `transparent_arc` | `true` | `arc` | 0.008789 | 0.012475 | 0.015811 | 0.01347 | 0.834573 | n/a |
| `transparent_arc_small` | `true` | `arc` | 0.008398 | 0.010995 | 0.012801 | 0.01161 | 0.817409 | n/a |
| `transparent_arc_thick` | `true` | `arc` | 0.010352 | 0.013744 | 0.016405 | 0.013752 | 0.850367 | n/a |
| `transparent_curve_s` | `true` | `stroke_path` | 0.017578 | 0.023259 | 0.019493 | 0.019555 | 0.891118 | n/a |
| `transparent_curve_wave` | `true` | `stroke_path` | 0.014258 | 0.017338 | 0.012667 | 0.015928 | 0.820741 | n/a |
| `transparent_curve_diagonal` | `true` | `stroke_path` | 0.018164 | 0.031082 | 0.019488 | 0.02103 | 0.903236 | n/a |
| `antialiased_circle` | `true` | `circle` | 0.005193 | 0.007324 | 0.012773 | 0.012611 | 0.929847 | n/a |
| `antialiased_circle_small` | `true` | `circle` | 0.004471 | 0.006287 | 0.010113 | 0.009792 | 0.911157 | n/a |
| `antialiased_circle_large` | `true` | `circle` | 0.009866 | 0.013717 | 0.022169 | 0.021303 | 0.958767 | n/a |
| `antialiased_ring` | `true` | `stroke_circle` | 0.019435 | 0.023825 | 0.024557 | 0.023357 | 0.946301 | n/a |
| `antialiased_ring_medium` | `true` | `stroke_circle` | 0.043551 | 0.041004 | 0.027218 | 0.027713 | 0.959586 | n/a |
| `antialiased_ring_large` | `true` | `stroke_circle` | 0.053777 | 0.050373 | 0.035531 | 0.034852 | 0.965777 | n/a |
| `antialiased_stroke_horizontal` | `true` | `stroke_polyline` | 0.006 | 0.006652 | 0.011203 | 0.006567 | 0.763341 | n/a |
| `antialiased_stroke_vertical` | `true` | `stroke_polyline` | 0.006048 | 0.006211 | 0.002253 | 0.002282 | 0.979167 | n/a |
| `antialiased_stroke_diagonal` | `true` | `stroke_polyline` | 0.020594 | 0.030997 | 0.012874 | 0.01856 | 0.976859 | n/a |
| `palette_drift_square` | `true` | `rect` | 1.5e-05 | 3.2e-05 | 1.5e-05 | 3.2e-05 | 1.0 | n/a |
| `palette_drift_rectangle` | `true` | `rect` | 1.8e-05 | 3.6e-05 | 1.8e-05 | 3.6e-05 | 1.0 | n/a |
| `palette_drift_circle` | `true` | `circle` | 1.5e-05 | 3.2e-05 | 0.010474 | 0.012803 | 1.0 | n/a |
| `transparent_circle` | `true` | `circle` | 0.0 | 0.0 | 0.004365 | 0.012008 | 1.0 | n/a |
| `transparent_circle_small` | `true` | `circle` | 0.0 | 0.0 | 0.003688 | 0.009564 | 1.0 | n/a |
| `transparent_circle_offset` | `true` | `circle` | 0.0 | 0.0 | 0.004112 | 0.011263 | 1.0 | n/a |
| `composition_same_color_two_squares` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `composition_same_color_square_circle` | `true` | `rect` | 0.0 | 0.0 | 0.006378 | 0.008011 | 1.0 | n/a |
| `composition_same_color_rect_circle` | `true` | `rect` | 0.0 | 0.0 | 0.005399 | 0.007296 | 1.0 | n/a |
| `composition_different_color_square_circle` | `true` | `rect` | 0.0 | 0.0 | 0.004961 | 0.006223 | 1.0 | n/a |
| `composition_different_color_two_rects` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `composition_different_color_circle_rect` | `true` | `circle` | 0.0 | 0.0 | 0.006161 | 0.007512 | 1.0 | n/a |
| `composition_circle_plus_horizontal_stroke` | `true` | `circle` | 0.0 | 0.0 | 0.010677 | 0.012769 | 1.0 | n/a |
| `composition_circle_plus_vertical_stroke` | `true` | `circle` | 0.0 | 0.0 | 0.010872 | 0.01298 | 1.0 | n/a |
| `composition_circle_plus_diagonal_stroke` | `true` | `circle` | 0.004492 | 0.009092 | 0.012721 | 0.020818 | 1.0 | n/a |
| `composition_square_plus_circle_a` | `true` | `rect` | 0.0 | 0.0 | 0.006378 | 0.008011 | 1.0 | n/a |
| `composition_square_plus_circle_b` | `true` | `rect` | 0.0 | 0.0 | 0.006378 | 0.008011 | 1.0 | n/a |
| `composition_square_plus_circle_c` | `true` | `rect` | 0.0 | 0.0 | 0.006378 | 0.008011 | 1.0 | n/a |
| `composition_ring_plus_dot_a` | `true` | `stroke_circle` | 0.030859 | 0.031294 | 0.020308 | 0.024446 | 0.976228 | n/a |
| `composition_ring_plus_dot_b` | `true` | `stroke_circle` | 0.030859 | 0.031294 | 0.020308 | 0.024446 | 0.976228 | n/a |
| `composition_ring_plus_dot_c` | `true` | `stroke_circle` | 0.030859 | 0.031294 | 0.020308 | 0.024446 | 0.976228 | n/a |
| `composition_dot_row_three` | `true` | `circle` | 0.0 | 0.0 | 0.008502 | 0.011181 | 1.0 | n/a |
| `composition_dot_row_four` | `true` | `circle` | 0.0 | 0.0 | 0.011336 | 0.014908 | 1.0 | n/a |
| `composition_dot_column_three` | `true` | `circle` | 0.0 | 0.0 | 0.008502 | 0.011181 | 1.0 | n/a |
| `composition_multiple_horizontal_strokes` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.010303 | 0.011365 | 1.0 | n/a |
| `composition_multiple_vertical_strokes` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.010302 | 0.011365 | 1.0 | n/a |
| `composition_multiple_mixed_strokes` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.013131 | 0.020949 | 1.0 | n/a |
| `adjacent_different_color_rects_horizontal` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_different_color_rects_vertical` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_different_color_rects_offset` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_same_color_rects_merge_horizontal` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_same_color_rects_merge_vertical` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_same_color_rects_merge_wide` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_small_gap_rects_horizontal` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_small_gap_rects_vertical` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `adjacent_small_gap_rects_offset` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `touching_circle_stroke_right` | `true` | `circle` | 0.0 | 0.0 | 0.009201 | 0.01111 | 1.0 | n/a |
| `touching_circle_stroke_left` | `true` | `circle` | 0.0 | 0.0 | 0.009803 | 0.011415 | 1.0 | n/a |
| `touching_circle_stroke_bottom` | `true` | `circle` | 0.0 | 0.0 | 0.009201 | 0.01111 | 1.0 | n/a |
| `stroke_crossing_rectangle_horizontal` | `true` | `rect` | 0.0 | 0.0 | 0.002994 | 0.002195 | 1.0 | n/a |
| `stroke_crossing_rectangle_vertical` | `true` | `rect` | 0.0 | 0.0 | 0.002994 | 0.002195 | 1.0 | n/a |
| `stroke_crossing_rectangle_low` | `true` | `rect` | 0.0 | 0.0 | 0.003189 | 0.00229 | 1.0 | n/a |
| `overlapping_rectangles_bottom_right` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `overlapping_rectangles_top_left` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `overlapping_rectangles_side` | `true` | `rect` | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | n/a |
| `cutout_horizontal_gap_center` | `true` | `rect` | 0.0 | 0.0 | 0.002905 | 0.003265 | 1.0 | n/a |
| `cutout_horizontal_gap_top` | `true` | `rect` | 0.0 | 0.0 | 0.002515 | 0.002842 | 1.0 | n/a |
| `cutout_horizontal_gap_bottom` | `true` | `rect` | 0.0 | 0.0 | 0.002515 | 0.002842 | 1.0 | n/a |
| `cutout_diagonal_gap_down` | `true` | `rect` | 0.003125 | 0.003595 | 0.00231 | 0.003418 | 1.0 | n/a |
| `cutout_diagonal_gap_up` | `true` | `rect` | 0.003516 | 0.004017 | 0.004702 | 0.006904 | 1.0 | n/a |
| `cutout_diagonal_gap_short` | `true` | `rect` | 0.002344 | 0.002749 | 0.001821 | 0.002728 | 1.0 | n/a |
| `organic_blob` | `true` | `cubic_path` | 0.012695 | 0.017761 | 0.015813 | 0.018444 | 0.927812 | n/a |
| `organic_blob_soft` | `true` | `cubic_path` | 0.014063 | 0.018607 | 0.016656 | 0.019543 | 0.93003 | n/a |
| `organic_blob_lumpy` | `true` | `cubic_path` | 0.010547 | 0.013955 | 0.014002 | 0.015984 | 0.957486 | n/a |
| `organic_leaf` | `true` | `cubic_path` | 0.010156 | 0.013109 | 0.012608 | 0.014354 | 0.95505 | n/a |
| `organic_leaf_narrow` | `true` | `cubic_path` | 0.009766 | 0.012264 | 0.013306 | 0.015255 | 0.954876 | n/a |
| `organic_leaf_tilted` | `true` | `cubic_path` | 0.009961 | 0.013955 | 0.0141 | 0.017042 | 0.953837 | n/a |
| `organic_asymmetric` | `true` | `cubic_path` | 0.010742 | 0.015435 | 0.012851 | 0.01607 | 0.943788 | n/a |
| `organic_asymmetric_heavy` | `true` | `cubic_path` | 0.011328 | 0.015224 | 0.012492 | 0.014533 | 0.965152 | n/a |
| `organic_asymmetric_soft` | `true` | `cubic_path` | 0.012109 | 0.01755 | 0.016244 | 0.018684 | 0.935299 | n/a |
| `organic_crescent` | `true` | `cubic_path` | 0.0125 | 0.017761 | 0.016305 | 0.019205 | 0.785124 | n/a |
| `organic_crescent_low` | `true` | `cubic_path` | 0.0125 | 0.017761 | 0.016305 | 0.019205 | 0.785124 | n/a |
| `organic_crescent_high` | `true` | `cubic_path` | 0.013672 | 0.018607 | 0.015335 | 0.018575 | 0.78564 | n/a |
| `organic_compound` | `true` | `cubic_path` | 0.013281 | 0.018607 | 0.016405 | 0.018991 | 0.920447 | n/a |
| `organic_compound_tall` | `true` | `cubic_path` | 0.012891 | 0.016493 | 0.015876 | 0.017453 | 0.924103 | n/a |
| `organic_compound_wide` | `true` | `cubic_path` | 0.012695 | 0.01607 | 0.015937 | 0.018091 | 0.94638 | n/a |
| `composition_arc_circle` | `true` | `arc` | 0.008594 | 0.012052 | 0.014842 | 0.018644 | 0.841652 | n/a |
| `composition_arc_circle_left` | `true` | `arc` | 0.007617 | 0.009938 | 0.01437 | 0.017295 | 0.828725 | n/a |
| `composition_arc_circle_small` | `true` | `arc` | 0.007617 | 0.009938 | 0.012863 | 0.015582 | 0.796157 | n/a |
| `composition_arc_rect` | `true` | `arc` | 0.007617 | 0.010784 | 0.009715 | 0.012167 | 0.881611 | n/a |
| `composition_arc_rect_side` | `true` | `arc` | 0.006836 | 0.010149 | 0.008995 | 0.011124 | 0.885139 | n/a |
| `composition_arc_rect_low` | `true` | `arc` | 0.00918 | 0.012264 | 0.009576 | 0.0115 | 0.877334 | n/a |
| `composition_curve_crossing_rect` | `true` | `rect` | 0.010807 | 0.010041 | 0.009906 | 0.009514 | 1.0 | n/a |
| `composition_curve_crossing_rect_high` | `true` | `rect` | 0.010807 | 0.010041 | 0.009906 | 0.009514 | 1.0 | n/a |
| `composition_curve_crossing_rect_wide` | `true` | `rect` | 0.010699 | 0.009613 | 0.010579 | 0.009081 | 1.0 | n/a |
| `composition_curve_touching_circle` | `true` | `circle` | 0.01033 | 0.013613 | 0.015459 | 0.018491 | 1.0 | n/a |
| `composition_curve_touching_circle_low` | `true` | `circle` | 0.009006 | 0.011131 | 0.014919 | 0.017426 | 1.0 | n/a |
| `composition_curve_touching_circle_left` | `true` | `circle` | 0.006793 | 0.008839 | 0.011427 | 0.014343 | 1.0 | n/a |
| `composition_ellipse_stroke` | `true` | `ellipse` | 0.010352 | 0.013955 | 0.013537 | 0.016393 | 0.934277 | n/a |
| `composition_ellipse_stroke_vertical` | `true` | `ellipse` | 0.010742 | 0.013109 | 0.012925 | 0.015735 | 0.934054 | n/a |
| `composition_ellipse_stroke_wide` | `true` | `ellipse` | 0.012695 | 0.015647 | 0.015351 | 0.018386 | 0.934412 | n/a |
| `composition_parallel_arcs` | `true` | `arc` | 0.015625 | 0.022413 | 0.020474 | 0.02504 | 0.836065 | n/a |
| `composition_parallel_arcs_tight` | `true` | `arc` | 0.017188 | 0.024739 | 0.021154 | 0.025352 | 0.879493 | n/a |
| `composition_parallel_arcs_three` | `true` | `arc` | 0.019922 | 0.02791 | 0.02685 | 0.031927 | 0.876236 | n/a |
| `composition_curve_group` | `true` | `stroke_path` | 0.029687 | 0.040597 | 0.027981 | 0.034353 | 0.869186 | n/a |
| `composition_curve_group_waves` | `true` | `stroke_path` | 0.025781 | 0.030025 | 0.022822 | 0.025685 | 0.81721 | n/a |
| `composition_curve_group_mixed` | `true` | `stroke_path` | 0.027148 | 0.037637 | 0.027136 | 0.033263 | 0.867267 | n/a |
| `cutout_curve_rect` | `true` | `quad` | 0.010156 | 0.010995 | 0.020327 | 0.022449 | 1.0 | n/a |
| `cutout_curve_rect_high` | `true` | `quad` | 0.007031 | 0.009092 | 0.017497 | 0.019273 | 1.0 | n/a |
| `cutout_curve_rect_low` | `true` | `quad` | 0.010547 | 0.010995 | 0.021073 | 0.023086 | 1.0 | n/a |
| `cutout_curve_circle` | `true` | `circle` | 0.004492 | 0.00592 | 0.019631 | 0.024067 | 1.0 | n/a |
| `cutout_curve_circle_large` | `true` | `circle` | 0.006641 | 0.008458 | 0.022633 | 0.027181 | 1.0 | n/a |
| `cutout_curve_circle_offset` | `true` | `circle` | 0.005273 | 0.006343 | 0.019497 | 0.023633 | 1.0 | n/a |
| `cutout_curve_ring` | `true` | `stroke_circle` | 0.068359 | 0.069565 | 0.060494 | 0.063313 | 0.95646 | n/a |
| `cutout_curve_ring_thick` | `true` | `stroke_circle` | 0.073047 | 0.068296 | 0.07271 | 0.072361 | 0.940919 | n/a |
| `cutout_curve_ring_offset` | `true` | `stroke_circle` | 0.069727 | 0.065124 | 0.056716 | 0.058195 | 0.951836 | n/a |
| `cutout_curve_crossing` | `true` | `quad` | 0.00293 | 0.003595 | 0.017186 | 0.02005 | 1.0 | n/a |
| `cutout_curve_crossing_low` | `true` | `quad` | 0.00293 | 0.003595 | 0.017186 | 0.02005 | 1.0 | n/a |
| `cutout_curve_crossing_right` | `true` | `quad` | 0.00293 | 0.003595 | 0.017186 | 0.02005 | 1.0 | n/a |
| `cutout_near_background` | `true` | `quad` | 0.010233 | 0.010936 | 0.02026 | 0.022272 | 1.0 | n/a |
| `cutout_near_background_light` | `true` | `quad` | 0.007273 | 0.00903 | 0.01748 | 0.019033 | 1.0 | n/a |
| `cutout_near_background_offwhite` | `true` | `quad` | 0.010623 | 0.010955 | 0.021012 | 0.022936 | 1.0 | n/a |
| `group_parallel_strokes_horizontal` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.010303 | 0.011365 | 1.0 | n/a |
| `group_parallel_strokes_vertical` | `true` | `stroke_polyline` | 0.0 | 0.0 | 0.010302 | 0.011365 | 1.0 | n/a |
| `group_parallel_strokes_diagonal` | `true` | `stroke_polyline` | 0.005273 | 0.010784 | 0.015033 | 0.030483 | 0.956614 | n/a |
| `group_dot_row_three` | `true` | `circle` | 0.0 | 0.0 | 0.008502 | 0.011181 | 1.0 | n/a |
| `group_dot_row_four` | `true` | `circle` | 0.0 | 0.0 | 0.011336 | 0.014908 | 1.0 | n/a |
| `group_dot_column_three` | `true` | `circle` | 0.0 | 0.0 | 0.008502 | 0.011181 | 1.0 | n/a |
| `group_quad_grid_row` | `true` | `quad` | 0.0 | 0.0 | 0.01857 | 0.021206 | 1.0 | n/a |
| `group_quad_grid_two_by_two` | `true` | `quad` | 0.0 | 0.0 | 0.029205 | 0.033002 | 1.0 | n/a |
| `group_quad_grid_column` | `true` | `quad` | 0.0 | 0.0 | 0.019256 | 0.021132 | 1.0 | n/a |
