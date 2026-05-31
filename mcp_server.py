from datetime import datetime, timezone
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import StreamingResponse
from mcp.server.fastmcp import FastMCP
from authsec_sdk import from_env, mount_mcp, ManifestTool, PolicyMode
import asyncio
import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

# ── MCP tools ────────────────────────────────────────────────────────────────

mcp = FastMCP("Simple MCP Server")


@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


@mcp.tool()
def get_time() -> str:
    """Get the current server time (UTC, ISO 8601)."""
    return datetime.now(timezone.utc).isoformat()


# ── Bridge: converts FastMCP's ASGI app into a handler mount_mcp can use ─────

mcp_asgi = mcp.streamable_http_app()


async def mcp_handler(request: Request):
    response_started = asyncio.Event()
    status_code = [200]
    resp_headers = [{}]
    body_queue: asyncio.Queue = asyncio.Queue()

    async def send(message):
        if message["type"] == "http.response.start":
            status_code[0] = message["status"]
            resp_headers[0] = {
                k.decode(): v.decode()
                for k, v in message.get("headers", [])
            }
            response_started.set()
        elif message["type"] == "http.response.body":
            await body_queue.put(
                (message.get("body", b""), message.get("more_body", False))
            )

    task = asyncio.create_task(mcp_asgi(request.scope, request.receive, send))
    await response_started.wait()

    async def body_stream():
        while True:
            chunk, more = await body_queue.get()
            yield chunk
            if not more:
                break
        await task

    return StreamingResponse(
        body_stream(),
        status_code=status_code[0],
        headers=resp_headers[0],
    )


# ── Tool inventory: tells AuthSec dashboard what tools exist ─────────────────

def tool_inventory():
    return [
        ManifestTool(
            name="add_numbers",
            description="Add two integers and return the sum.",
            input_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            suggested_scopes=["read"],
        ),
        ManifestTool(
            name="get_time",
            description="Get the current server time (UTC, ISO 8601).",
            input_schema={"type": "object", "properties": {}},
            suggested_scopes=["read"],
        ),
    ]
    

cfg = from_env()
cfg.publish_manifest = True
cfg.tool_inventory_provider = tool_inventory
cfg.tool_scopes = {"add_numbers": ["read"], "get_time": ["read"]}
cfg.policy_mode = PolicyMode.REMOTE_WITH_LOCAL_FALLBACK

app = FastAPI()

# Registers /mcp (protected) and /.well-known/oauth-protected-resource/mcp
mount_mcp(app, "/mcp", mcp_handler, cfg)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
