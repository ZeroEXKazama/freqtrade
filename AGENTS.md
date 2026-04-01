# Freqtrade Development Guide

## Cursor Cloud specific instructions

### Overview
Freqtrade is a Python-based cryptocurrency trading bot. It is a single-process application with no external services required (uses embedded SQLite). The only system-level dependency is the **TA-Lib C library**.

### Running commands
All commands use the `freqtrade` CLI entry point. Ensure `~/.local/bin` is on `PATH`:
```
export PATH="$HOME/.local/bin:$PATH"
```

### Lint / Type-check / Test
- **Lint**: `ruff check .` (see `pyproject.toml` for config)
- **Type-check**: `mypy freqtrade` — 2 pre-existing errors in `webserver.py` related to FastAPI `add_event_handler` deprecation
- **Test**: `pytest tests/ --timeout=120 -p no:randomly --ignore=tests/exchange_online`
  - Tests in `tests/exchange_online/` require live exchange connectivity; skip them in Cloud Agent VMs
  - Tests in `tests/commands/test_commands.py` for `test_start_list_strategies` and `test_start_list_hyperopt_loss_functions` may fail due to Rich table column truncation at narrow terminal widths — this is a pre-existing issue, not a setup problem
  - Tests in `tests/rpc/test_rpc_apiserver.py` have pre-existing errors due to FastAPI `add_event_handler` removal in newer versions

### Backtesting (hello world)
To verify the environment works end-to-end without exchange connectivity:
```
freqtrade backtesting --config tests/testdata/config.tests.json -s SampleStrategy --datadir tests/testdata --timerange 20180110-20180301
```

### Exchange connectivity
Cloud Agent VMs may not be able to reach certain exchange APIs (e.g. Binance returns HTTP 451 from restricted locations). This does not affect backtesting with local data or running the test suite.

### Dependencies
Install for development with `pip install -e ".[dev]"`. This installs all optional extras (FreqAI, plotting, hyperopt, jupyter) plus dev tooling (pytest, ruff, mypy, pre-commit).
