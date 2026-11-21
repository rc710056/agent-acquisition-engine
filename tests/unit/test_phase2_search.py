import pytest
from services.mcp_server.server import search_sources, mcp

@pytest.mark.asyncio
async def test_search_sources_empty_query_fails():
    res = await search_sources(query="")
    assert res["ok"] is False
    assert res["error_code"] == "INVALID_ARGUMENT"
    assert "empty" in res["error"].lower()

@pytest.mark.asyncio
async def test_search_sources_movie_intelligence_query():
    res = await search_sources(query="Iron Man", kind="movie", max_results=3)
    assert res["ok"] is True
    assert res["results_count"] >= 1
    candidates = res["candidates"]
    assert any("Iron Man" in c["title"] for c in candidates)
    # Theatrical movie should have OTT platforms and director
    theatrical = next((c for c in candidates if c.get("candidate_type") == "movie_intelligence"), None)
    assert theatrical is not None
    assert len(theatrical.get("ott_platforms", [])) >= 1
    assert theatrical.get("director") is not None

@pytest.mark.asyncio
async def test_search_sources_media_platform_query():
    res = await search_sources(query="Big Buck Bunny", kind="video", max_results=2)
    assert res["ok"] is True
    assert res["results_count"] >= 1
    candidates = res["candidates"]
    assert any("Big Buck Bunny" in c["title"] for c in candidates)

@pytest.mark.asyncio
async def test_search_sources_registered_in_fastmcp():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "search_sources" in tool_names
    assert "describe_capabilities" in tool_names
