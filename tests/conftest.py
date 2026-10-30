import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('make_fixtures', Path(__file__).parents[1] / 'scripts' / 'make_fixtures.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


@pytest.fixture
def site(tmp_path):
    fixtures.generate(tmp_path)
    return tmp_path
