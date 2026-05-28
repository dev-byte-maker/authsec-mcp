from datetime import datetime, timezone
from authsec_sdk import run_mcp_server_with_oauth, protected_by_AuthSec
import os
import sys
from dotenv import load_dotenv

load_dotenv()

@protected_by_AuthSec(
    "add_numbers",
    scopes=["read"],
    description="Add two integers and return the sum.",
    inputSchema={
        "type": "object",
        "properties": {
            "a": {"type": "integer"},
            "b": {"type": "integer"},
        },
        "required": ["a", "b"],
    },
)
async def add_numbers(arguments: dict) -> int:
    """Add two integers and return the sum."""
    return arguments["a"] + arguments["b"]


@protected_by_AuthSec(
    "get_time",
    scopes=["read"],
    description="Get the current server time (UTC, ISO 8601).",
    inputSchema={"type": "object", "properties": {}},
)
async def get_time(arguments: dict) -> str:
    """Get the current server time (UTC, ISO 8601)."""
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    client_id = (
        os.getenv("AUTHSEC_CLIENT_ID")
        or os.getenv("AUTHSEC_INTROSPECTION_CLIENT_ID")
        or ""
    )
    run_mcp_server_with_oauth(
        sys.modules[__name__],
        client_id=client_id,
        app_name="Mcp server -1",
        host="0.0.0.0",
        port=8080,
    )
