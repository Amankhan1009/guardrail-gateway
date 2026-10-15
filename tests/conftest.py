"""
Pytest configuration and shared fixtures for the Guardrail Gateway test suite.
Ensures clean test isolation and zero-cost mock harnesses.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.policies.rate_limiter import rate_limiter


@pytest.fixture(autouse=True)
def clean_rate_limiter():
    """
    Autouse fixture that clears the in-memory rate limiter history before every test.
    This guarantees that tests never bleed rate-limit state into subsequent tests.
    """
    rate_limiter._history.clear()
    yield
    rate_limiter._history.clear()


@pytest.fixture
def client():
    """
    Provides a FastAPI TestClient for in-memory HTTP request dispatching.
    """
    with TestClient(app) as test_client:
        yield test_client