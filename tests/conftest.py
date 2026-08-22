import pytest

from recon.generate_data import generate
from recon.pipeline import run


@pytest.fixture(scope="session", autouse=True)
def build_reports():
    """The agent tests read real reports/*.csv and data/generated/*.csv --
    build them once, deterministically, before anything else runs."""
    generate(seed=42)
    run()
