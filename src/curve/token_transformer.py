"""Small deterministic token encoder shared by MLX training artifacts."""

from __future__ import annotations

from math import exp, sqrt, tanh


RGBA_TOKEN_WIDTH = 7
TOKEN_PROJECTION_INPUT_NAMES = (
    "red_or_feature",
    "green",
    "blue",
    "alpha",
    "x_or_feature_position",
    "y",
    "foreground_or_abs_feature",
    "token_position",
)


def token_transformer_embedding(
    features: tuple[float, ...],
    crop_tokens: tuple[tuple[float, float, float, float], ...],
    *,
    crop_size: int,
    hidden_dim: int,
    heads: int,
    layers: int,
    raster_grid_size: int = 4,
    projection_scale: tuple[float, ...] | None = None,
    projection_bias: tuple[float, ...] | None = None,
    projection_weights: tuple[tuple[float, ...], ...] | None = None,
    projection_intercept: tuple[float, ...] | None = None,
) -> tuple[float, ...]:
    """Encode geometric features and pooled RGBA crop tokens into one vector."""

    hidden_dim = max(1, hidden_dim)
    heads = max(1, heads)
    layers = max(1, layers)
    tokens = token_transformer_tokens(
        features,
        crop_tokens,
        crop_size=crop_size,
        raster_grid_size=raster_grid_size,
    )
    if not tokens:
        return tuple(0.0 for _ in range(hidden_dim))

    hidden = [
        _project_token(
            token,
            token_index=index,
            hidden_dim=hidden_dim,
            projection_scale=projection_scale,
            projection_bias=projection_bias,
            projection_weights=projection_weights,
            projection_intercept=projection_intercept,
        )
        for index, token in enumerate(tokens)
    ]
    for layer_index in range(layers):
        hidden = _self_attention_layer(
            hidden,
            heads=heads,
            layer_index=layer_index,
        )
    return tuple(
        sum(token[hidden_index] for token in hidden) / len(hidden)
        for hidden_index in range(hidden_dim)
    )


def raster_grid_token_count(crop_size: int, raster_grid_size: int = 4) -> int:
    grid_size = max(1, min(raster_grid_size, crop_size))
    return grid_size * grid_size


def token_transformer_tokens(
    features: tuple[float, ...],
    crop_tokens: tuple[tuple[float, float, float, float], ...],
    *,
    crop_size: int,
    raster_grid_size: int = 4,
) -> list[tuple[float, ...]]:
    return _feature_tokens(features) + _pooled_raster_tokens(
        crop_tokens,
        crop_size=crop_size,
        grid_size=raster_grid_size,
    )


def _feature_tokens(features: tuple[float, ...]) -> list[tuple[float, ...]]:
    count = max(1, len(features))
    tokens: list[tuple[float, ...]] = []
    for index, value in enumerate(features):
        bounded = value / (abs(value) + 1.0) if value else 0.0
        tokens.append(
            (
                bounded,
                0.0,
                0.0,
                1.0,
                index / max(1, count - 1),
                0.0,
                abs(bounded),
            )
        )
    return tokens


def _pooled_raster_tokens(
    crop_tokens: tuple[tuple[float, float, float, float], ...],
    *,
    crop_size: int,
    grid_size: int,
) -> list[tuple[float, ...]]:
    grid_size = max(1, min(grid_size, crop_size))
    buckets = [
        [0.0 for _ in range(RGBA_TOKEN_WIDTH + 1)]
        for _ in range(grid_size * grid_size)
    ]
    for index, token in enumerate(crop_tokens):
        red, green, blue, alpha = token
        x_index = index % crop_size
        y_index = index // crop_size
        x = x_index / max(1, crop_size - 1)
        y = y_index / max(1, crop_size - 1)
        bucket_x = min(grid_size - 1, int(x_index * grid_size / max(1, crop_size)))
        bucket_y = min(grid_size - 1, int(y_index * grid_size / max(1, crop_size)))
        bucket = buckets[bucket_y * grid_size + bucket_x]
        foreground = alpha * (
            abs(red - 1.0) + abs(green - 1.0) + abs(blue - 1.0)
        ) / 3
        for value_index, value in enumerate((red, green, blue, alpha, x, y, foreground)):
            bucket[value_index] += value
        bucket[-1] += 1.0
    tokens: list[tuple[float, ...]] = []
    for bucket in buckets:
        count = bucket[-1]
        if count <= 0:
            tokens.append(tuple(0.0 for _ in range(RGBA_TOKEN_WIDTH)))
            continue
        tokens.append(tuple(value / count for value in bucket[:-1]))
    return tokens


def _project_token(
    token: tuple[float, ...],
    *,
    token_index: int,
    hidden_dim: int,
    projection_scale: tuple[float, ...] | None,
    projection_bias: tuple[float, ...] | None,
    projection_weights: tuple[tuple[float, ...], ...] | None,
    projection_intercept: tuple[float, ...] | None,
) -> tuple[float, ...]:
    position = (token_index + 1) / 64
    projected: list[float] = []
    learned_inputs = (*token, position)
    for hidden_index in range(hidden_dim):
        learned_row = (
            projection_weights[hidden_index]
            if projection_weights is not None
            and hidden_index < len(projection_weights)
            else None
        )
        if (
            learned_row is not None
            and len(learned_row) == len(learned_inputs)
            and projection_intercept is not None
            and hidden_index < len(projection_intercept)
        ):
            value = tanh(
                sum(
                    learned_row[input_index] * learned_inputs[input_index]
                    for input_index in range(len(learned_inputs))
                )
                + projection_intercept[hidden_index]
            )
        else:
            value = tanh(
                token[hidden_index % len(token)] * (1.0 + (hidden_index % 5) * 0.2)
                + position * ((hidden_index % 3) - 1)
            )
        if (
            projection_scale is not None
            and projection_bias is not None
            and hidden_index < len(projection_scale)
            and hidden_index < len(projection_bias)
        ):
            value = tanh(
                value * projection_scale[hidden_index]
                + projection_bias[hidden_index]
            )
        projected.append(value)
    return tuple(projected)


def _self_attention_layer(
    hidden: list[tuple[float, ...]],
    *,
    heads: int,
    layer_index: int,
) -> list[tuple[float, ...]]:
    hidden_dim = len(hidden[0])
    slices = _head_slices(hidden_dim, min(heads, hidden_dim))
    next_hidden: list[tuple[float, ...]] = []
    for token in hidden:
        attended_values: list[float] = []
        for start, end in slices:
            query = token[start:end]
            scores = [
                sum(query[index] * other[start + index] for index in range(end - start))
                / sqrt(max(1, end - start))
                for other in hidden
            ]
            weights = _softmax(scores)
            for feature_index in range(start, end):
                attended_values.append(
                    sum(
                        weight * other[feature_index]
                        for weight, other in zip(weights, hidden)
                    )
                )
        next_hidden.append(
            tuple(
                tanh((token[index] + attended_values[index]) / 2 + layer_index * 0.01)
                for index in range(hidden_dim)
            )
        )
    return next_hidden


def _head_slices(hidden_dim: int, heads: int) -> list[tuple[int, int]]:
    head_count = max(1, min(heads, hidden_dim))
    base_width = max(1, hidden_dim // head_count)
    slices: list[tuple[int, int]] = []
    start = 0
    for head in range(head_count):
        end = hidden_dim if head == head_count - 1 else min(hidden_dim, start + base_width)
        slices.append((start, end))
        start = end
    return slices


def _softmax(values: list[float]) -> list[float]:
    offset = max(values)
    exps = [exp(value - offset) for value in values]
    total = sum(exps)
    return [value / total for value in exps]
