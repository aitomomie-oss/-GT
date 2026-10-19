"""Regression/UI tests never start real market network worker threads."""
import pytest

@pytest.fixture(autouse=True)
def no_background_network(monkeypatch):
    monkeypatch.setenv('MY_AI_ASSET_DISABLE_BACKGROUND','1')
