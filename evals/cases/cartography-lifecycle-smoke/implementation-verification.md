# Implementation verification

- TDD RED: `python -m pytest tests/integration/test_export_cli.py -q` exited 1 before the export entrypoint and CLI registration existed.
- TDD GREEN: `python -m pytest tests/integration/test_export_cli.py -q` exited 0 after implementation.
- full tests: `python -m pytest -q` exited 0.
- lint: `ruff check .` exited 0 with no warnings.
- typecheck: `mypy src` exited 0.
- CLI smoke: `message-hub export attachment-1 --out /tmp/export` exited 0 and wrote the fixture bytes.
