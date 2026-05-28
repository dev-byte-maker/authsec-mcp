from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
import uvicorn

mcp = FastMCP("Simple MCP Server")

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b

@mcp.tool()
def get_time() -> str:
    """Get the current server time (UTC, ISO 8601)."""
    return datetime.now(timezone.utc).isoformat()

if __name__ == "__main__":
    app = mcp.streamable_http_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],            # lock this down in production
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)