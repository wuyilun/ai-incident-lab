from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from apps.agent import main


@pytest.mark.asyncio
async def test_provider_error_text_is_not_published(monkeypatch):
    client = AsyncMock()

    @asynccontextmanager
    async def connection(*args):
        yield client

    monkeypatch.setattr(main, "connect", connection)
    monkeypatch.setattr(
        main, "run_reference", AsyncMock(side_effect=RuntimeError("Bearer synthetic-private-value"))
    )
    result = await main.execute(
        main.RunRequest(incident_id="test", run_id="test", token="dummy", mode="reference")
    )
    assert result == {"status": "failed", "error": "RuntimeError"}
    client.call.assert_awaited_once_with("fail_incident", reason="RuntimeError")
