import sys
from pathlib import Path

import pytest

# lang/ is importable on its own, without the add-on package (and without bpy)
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "addons" / "bnodes"))

from fake_schema import FakeSchema  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def schema():
    return FakeSchema()


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text()
