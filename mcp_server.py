from datetime import datetime, timezone
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from mcp.server.fastmcp import FastMCP
from authsec_sdk import from_env, mount_mcp
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


# ── Bridge FastMCP's ASGI app to a Starlette route handler for mount_mcp ────

mcp_asgi = mcp.streamable_http_app()


async def mcp_handler(request: Request):
    """Converts FastMCP's ASGI app into a handler compatible with mount_mcp."""
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


# ── App setup following the docs: from_env() + mount_mcp() ──────────────────

cfg = from_env()

app = Starlette()

# mount_mcp registers /mcp (protected) and
# /.well-known/oauth-protected-resource/mcp (RFC 9728 metadata) automatically
mount_mcp(app, "/mcp", mcp_handler, cfg)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
