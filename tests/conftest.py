import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR

@pytest.fixture
def clawhavoc_skill(fixtures_dir: Path) -> Path:
    return fixtures_dir / "clawhavoc-skill.md"

@pytest.fixture
def overpermissioned_skill(fixtures_dir: Path) -> Path:
    return fixtures_dir / "overpermissioned-skill.md"

@pytest.fixture
def clean_skill(fixtures_dir: Path) -> Path:
    return fixtures_dir / "clean-skill.md"

@pytest.fixture
def tmp_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "test-run"
    run_dir.mkdir()
    return run_dir
