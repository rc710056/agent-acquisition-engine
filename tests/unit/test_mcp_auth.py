import pytest
import httpx

from apps.api.app.main import app
from services.mcp_server.server import get_user_dashboard_link, mcp


@pytest.mark.asyncio
async def test_mcp_tool_schemas_do_not_accept_credentials():
    tools = await mcp.list_tools()
    for tool in tools:
        properties = tool.input_schema.get("properties", {})
        assert "api_key" not in properties
        assert "token" not in properties
        assert "portal_token" not in properties


@pytest.mark.asyncio
async def test_dashboard_link_rejects_agent_and_missing_credentials():
    agent_result = await get_user_dashboard_link(api_key="aae_live_test_key")
    anonymous_result = await get_user_dashboard_link()

    assert "error" in agent_result
    assert "portal credential is required" in agent_result["error"].lower()
    assert "portal_token" not in agent_result
    assert "error" in anonymous_result


@pytest.mark.asyncio
async def test_remote_mcp_transport_requires_bearer_token():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/mcp/sse")

    assert response.status_code == 401
