# Development

Use Python 3.11. Create a virtual environment, then install `.[dev]`; add `.[desktop]` or
`.[inference]` only for those workflows. Models and public datasets belong outside Git.

Quality gate:

```bash
ruff format --check .
ruff check .
mypy src
pytest --cov=npu_scribe
python -m build
```

The Windows build must be produced on Windows because PyInstaller does not cross-build.
Do not commit, publish, or invoke the trusted `sandboxctl` launcher from the container.
Never add model weights or personal media. New platform behavior requires a mock contract
test plus a bounded owner-run Windows check.
