"""Пример Hypothesis-теста против локального Prism, не реального API."""

import os

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


@pytest.mark.prism
@pytest.mark.skipif(
    os.environ.get("RUN_PRISM_TESTS") != "1",
    reason="Запустите локальный Prism и установите RUN_PRISM_TESTS=1",
)
@pytest.mark.asyncio
@settings(max_examples=10, deadline=None)
@given(
    suffix=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789- _", min_size=1, max_size=20
    )
)
async def test_egr_accepts_string_query(suffix: str) -> None:
    req = f"test-{suffix}"
    port = int(os.environ.get("PRISM_TEST_PORT", "4010"))
    if not 1 <= port <= 65535:
        raise ValueError("PRISM_TEST_PORT must be between 1 and 65535")
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}", timeout=5.0, trust_env=False
    ) as client:
        response = await client.get("/egr", params={"req": req, "key": "test-key"})

    assert response.status_code == 200
    assert response.request.url.params["req"] == req
    assert isinstance(response.json(), dict)
