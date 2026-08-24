from __future__ import annotations


def create_server():
    try:
        from mcp.server import MCPServer
    except ImportError as exc:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("install ARL with the 'mcp' extra to run the demo server") from exc

    server = MCPServer("arl-demo")

    @server.tool()
    def echo(text: str) -> dict[str, str]:
        """Return text unchanged."""
        return {"value": text}

    @server.tool()
    def add(left: int, right: int) -> dict[str, int]:
        """Add two integers."""
        return {"value": left + right}

    @server.tool()
    def submit_demo(value: str) -> dict[str, str]:
        """Synthetic irreversible action; ARL must block it in SAFE_LIVE."""
        return {"submitted": value}

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
