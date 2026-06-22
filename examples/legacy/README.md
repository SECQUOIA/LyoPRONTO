# Legacy Example Scripts

This directory keeps the original LyoPRONTO example scripts for backward
compatibility and regression coverage:

- `ex_knownRp_PD.py`: primary drying with known product resistance.
- `ex_unknownRp_PD.py`: product-resistance estimation from temperature data.

Run them from this directory because they use local relative paths:

```bash
cd examples/legacy
python ex_knownRp_PD.py
python ex_unknownRp_PD.py
```

The scripts generate timestamped CSV/PDF outputs in the current directory.
Those generated files are ignored by git and should not be committed.

For new work, prefer the maintained examples in `examples/`:

| Legacy script | Maintained equivalent |
| --- | --- |
| `ex_knownRp_PD.py` | `example_web_interface.py` |
| `ex_unknownRp_PD.py` | `example_parameter_estimation.py` |

Legacy script execution is covered by `tests/test_example_scripts.py`:

```bash
pytest tests/test_example_scripts.py -v
```

See `../README.md` for maintained examples and `../../docs/how-to-guides.md`
for setup and local validation.
