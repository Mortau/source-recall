from __future__ import annotations

import asyncio

import pytest
from fastmcp import Client

from source_recall import mcp_server
from source_recall.config import Settings

EXPECTED_TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


def test_mcp_tools_advertise_read_only_annotations() -> None:
    async def scenario():
        server = mcp_server.create_mcp(
            Settings.from_mapping({"logging": {"file": None}})
        )
        async with Client(server) as client:
            return await client.list_tools()

    tools = asyncio.run(scenario())

    assert {tool.name for tool in tools} == {
        "search_codebase",
        "get_file",
        "list_repositories",
        "get_index_status",
    }
    for tool in tools:
        assert tool.annotations is not None
        annotations = tool.annotations.model_dump(exclude_none=True)
        assert annotations == EXPECTED_TOOL_ANNOTATIONS
        assert all(isinstance(value, bool) for value in annotations.values())


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_request"),
    [
        (
            "search_codebase",
            {"repository": "example", "query": "entry point", "limit": 3},
            (
                "POST",
                "/search",
                {
                    "json": {
                        "repository": "example",
                        "query": "entry point",
                        "limit": 3,
                    }
                },
            ),
        ),
        (
            "get_file",
            {"repository": "example", "path": "/src/a b.py"},
            ("GET", "/file/example/src/a%20b.py", {}),
        ),
        ("list_repositories", {}, ("GET", "/repositories", {})),
        ("get_index_status", {}, ("GET", "/status", {})),
    ],
)
def test_mcp_tools_route_to_api(
    monkeypatch,
    tool_name,
    arguments,
    expected_request,
) -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    async def fake_request(self, method, path, **kwargs):
        requests.append((method, path, kwargs))
        return {"tool": tool_name}

    monkeypatch.setattr(mcp_server.SourceRecallApiClient, "request", fake_request)
    server = mcp_server.create_mcp(
        Settings.from_mapping({"logging": {"file": None}})
    )

    async def scenario():
        async with Client(server) as client:
            return await client.call_tool(tool_name, arguments)

    result = asyncio.run(scenario())

    assert result.structured_content == {"tool": tool_name}
    assert requests == [expected_request]


def test_http_mcp_transport_is_stateless(monkeypatch) -> None:
    settings = Settings.from_mapping(
        {
            "mcp": {"transport": "http"},
            "logging": {"file": None},
        }
    )
    run_arguments: dict[str, object] = {}

    monkeypatch.setattr(
        mcp_server.Settings,
        "load",
        classmethod(lambda cls: settings),
    )
    monkeypatch.setattr(
        mcp_server.FastMCP,
        "run",
        lambda self, **kwargs: run_arguments.update(kwargs),
    )

    mcp_server.main()

    assert run_arguments == {
        "transport": "http",
        "host": settings.mcp.host,
        "port": settings.mcp.port,
        "path": settings.mcp.path,
        "stateless_http": True,
    }
