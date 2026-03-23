# Contributing to clawagentskill

## Development Setup

```bash
git clone https://github.com/austinmao/clawagentskill.git
cd clawagentskill
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## Adding a Scanner

1. Create `src/clawagentskill/scan/your_scanner.py`
2. Implement a function matching this signature:
   ```python
   def scan_yourscanner(path: Path) -> dict[str, Any]:
       return {
           "scanner": "your-scanner",
           "status": "clean",  # clean | warn | blocked | error | skipped
           "skill_path": str(path.resolve()),
           "scanned_at": datetime.now(timezone.utc).isoformat(),
           "findings": [],
       }
   ```
3. Register in `src/clawagentskill/scan/runner.py` `SCANNER_MAP`
4. Add `"your-scanner"` to the default scanners list in `config.py`
5. Write tests in `tests/test_scanners.py`

## Adding a Registry

1. Create `src/clawagentskill/discover/your_registry.py`
2. Implement `search(query, max_results) -> list[dict]` returning SkillCandidate dicts
3. Wire into `cli.py` `_cmd_find()` and `pipeline.py` search stage
4. Add default config in `config.py`

## Adding a Translator

1. Create `src/clawagentskill/translate/your_format.py`
2. Implement `translate(content: str) -> str` returning SOUL.md content
3. Add to the fallback chain in `translate/skillkit.py`

## Running Tests

```bash
.venv/bin/pytest                    # All tests
.venv/bin/pytest tests/test_scanners.py  # Scanner tests only
.venv/bin/pytest -v                 # Verbose output
```

## Code Style

- Python 3.11+
- `from __future__ import annotations` in every file
- Immutable data (frozen dataclasses, return new dicts)
- Type hints on all public functions
- No mutation of function arguments
