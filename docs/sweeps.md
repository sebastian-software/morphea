# Config Sweeps

`curve sweep` runs one input image through multiple bounded vectorize configs
and writes comparable run directories.

## Schema

```json
{
  "version": 1,
  "input": "input.png",
  "runs": [
    {
      "id": "baseline",
      "config": {
        "min_area": 8,
        "timeout_seconds": 5
      }
    },
    {
      "id": "tolerant-small",
      "config": {
        "min_area": 12,
        "color_tolerance": 18,
        "max_size": 256,
        "max_colors": 10,
        "max_component_area": 12000,
        "timeout_seconds": 8
      }
    }
  ]
}
```

Supported config keys match the current `vectorize` runtime knobs:

- `min_area`
- `color_tolerance`
- `max_size`
- `max_colors`
- `max_component_area`
- `timeout_seconds`
- `classifier_model`

Run:

```sh
PYTHONPATH=src python3 -m curve.cli sweep sweep.json -o runs/sweep
```

Output:

- `runs/sweep/<run-id>/output.svg`
- `runs/sweep/<run-id>/manifest.json`
- `runs/sweep/<run-id>/config.json`
- `runs/sweep/<run-id>/report.md`
- `runs/sweep/sweep-summary.json`
