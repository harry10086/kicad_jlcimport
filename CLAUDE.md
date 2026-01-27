# Project Notes

## BEFORE COMMITTING - MANDATORY BUILD CHECKS

**NEVER COMMIT WITHOUT RUNNING ALL THREE CHECKS:**

```bash
# Run from project root directory
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m pytest tests/ -q --cov=src --cov-fail-under=80
```

ALL THREE must pass with zero errors before any commit or push.

## PROJECT STRUCTURE

This project uses the standard **src layout**. The package source lives in `src/kicad_jlcimport/`.

```
src/kicad_jlcimport/         # main package
├── easyeda/                  # EasyEDA data fetching, types, and parsing
├── kicad/                    # KiCad file generation and library management
├── gui/                      # wxPython GUI
├── tui/                      # Textual TUI
├── importer.py               # import orchestration
└── ...
tests/                        # test suite
tools/                        # developer utilities (not part of the package)
```

To run code that imports the package, set `PYTHONPATH` to the `src/` directory:
```bash
PYTHONPATH=src python3 -c "from kicad_jlcimport.easyeda.parser import ..."
```

## FIXING TEST FAILURES

**Understand the root cause before changing anything.** Don't jump to the first edit that makes tests pass.

- **Never modify production code just to make a test pass.** If a test fails, first determine whether the test or the production code is wrong. Read the production code's docstrings, comments, and recent commit history before deciding.
- **Treat merged/reviewed production code as intentional.** If code is deliberately designed a certain way (especially error handling, security boundaries, or API contracts), fix the tests to match the design — not the other way around.
- **Mock external dependencies.** When tests fail because they make real network, filesystem, or OS calls, mock the external dependency. Don't weaken production error handling to tolerate environment differences.
