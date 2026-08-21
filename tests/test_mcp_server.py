from __future__ import annotations

from source_recall import mcp_server
from source_recall.config import Settings


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
