# Project Notes

## BEFORE COMMITTING - MANDATORY BUILD CHECKS

**NEVER COMMIT WITHOUT RUNNING ALL THREE CHECKS:**

```bash
# Run from project root directory (/Users/joshv/git/kicad_jlcimport)
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m pytest tests/ -q --cov=. --cov-fail-under=80
```

ALL THREE must pass with zero errors before any commit or push.

## IMPORTANT: RUNNING PYTHON IN THIS PROJECT

**THE PROJECT DIRECTORY IS THE PACKAGE. SET PYTHONPATH TO THE PARENT!**

The `kicad_jlcimport` directory IS the package, so imports like `from kicad_jlcimport.parser import ...` require the PARENT directory in PYTHONPATH.

WRONG:
```bash
PYTHONPATH=. python3 -c "from kicad_jlcimport.parser import ..."
```

RIGHT:
```bash
cd /Users/joshv/git && PYTHONPATH=. python3 -c "from kicad_jlcimport.parser import ..."
```

OR use existing scripts that handle the path (like convert_testdata.py).

## FIXING TEST FAILURES

**Understand the root cause before changing anything.** Don't jump to the first edit that makes tests pass.

- **Never modify production code just to make a test pass.** If a test fails, first determine whether the test or the production code is wrong. Read the production code's docstrings, comments, and recent commit history before deciding.
- **Treat merged/reviewed production code as intentional.** If code is deliberately designed a certain way (especially error handling, security boundaries, or API contracts), fix the tests to match the design — not the other way around.
- **Mock external dependencies.** When tests fail because they make real network, filesystem, or OS calls, mock the external dependency. Don't weaken production error handling to tolerate environment differences.
