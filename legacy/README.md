# Legacy modules

These files were the early prototypes and have been superseded by the
current `screen_v3.py` + `screen_core.py` + `signals.py` pipeline.
Kept here for archaeology — they no longer satisfy the current `params`
contracts and shouldn't be run.

| File | Replaced by |
|---|---|
| `screen_v2.py` | `screen_v3.py` |
| `nav_discount_finder.py` | `screen_core.py` (logic) + `screen_v3.py` (pipeline) |
| `qualitative_signals.py` | `signals.py` (v2 layer + Investegate RNS) |
| `run_screen.py` | direct invocation of `python3 screen_v3.py` |
