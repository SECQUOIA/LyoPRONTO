# Legacy Example Scripts

This directory keeps the original LyoPRONTO example scripts as archival
provenance:

- `ex_knownRp_PD.py`: primary drying with known product resistance.
- `ex_unknownRp_PD.py`: product-resistance estimation from temperature data.

They are snapshots of the pre-package, working-directory workflow and are not
maintained execution targets. In particular, `ex_unknownRp_PD.py` names the
historical local `temperature.dat`; that normalization-only data copy is no
longer tracked. The canonical measured input is
`../../test_data/temperature.txt` and maintained code loads it through
`examples.original_workflow_parity`.

For new work, prefer the maintained examples in `examples/`:

| Legacy script | Maintained equivalent |
| --- | --- |
| `ex_knownRp_PD.py` | `example_web_interface.py` |
| `ex_unknownRp_PD.py` | `example_parameter_estimation.py` |

The maintained replacements are the original-workflow notebooks, which import
canonical computations and are fresh-kernel tested:

```bash
pytest tests/test_original_workflow_notebooks.py -v
```

See `../README.md` for maintained examples and `../../docs/how-to-guides.md`
for setup and local validation.
