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
