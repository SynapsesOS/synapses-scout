"""Shared test fixtures."""

import pytest

from scout.config import ScoutConfig


@pytest.fixture
def config(tmp_path):
    return ScoutConfig(
        db_path=str(tmp_path / "test_scout.db"),
        intelligence_url="http://localhost:11435",
        distill=False,
    )
