from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from starlette.requests import Request
from mcp.server.fastmcp import FastMCP
from authsec_sdk import from_env, mount_mcp, ManifestTool, PolicyMode
from authsec_sdk.runtime.metadata import build_resource_metadata_path, metadata_json_response
import json
import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

# ── MCP tools ─────────────────────────────────────────────────────────────────

mcp = FastMCP("Simple MCP Server")


@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


@mcp.tool()
def get_time() -> str:
    """Get the current server time (UTC, ISO 8601)."""
    return datetime.now(timezone.utc).isoformat()


# ── MCP handler using FastMCP's direct API (no ASGI bridge needed) ────────────

async def mcp_handler(request: Request):
    body = await request.body()
    try:
        msg = json.loads(body)
    except json.JSONDecodeError as exc:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}})

    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "Simple MCP Server", "version": "1.0.0"},
            },
        })

    if method == "notifications/initialized":
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

    if method == "tools/list":
        tools = await mcp.list_tools()
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.inputSchema,
                    }
                    for t in tools
                ]
            },
        })

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            result = await mcp.call_tool(tool_name, arguments)
            content = [{"type": "text", "text": str(r)} for r in result] if isinstance(result, list) else [{"type": "text", "text": str(result)}]
        except Exception as exc:
            content = [{"type": "text", "text": str(exc)}]
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}})

    return JSONResponse({
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    })


# ── AuthSec config ─────────────────────────────────────────────────────────────

cfg = from_env()
cfg.publish_manifest = True
cfg.policy_mode = PolicyMode.REMOTE_WITH_LOCAL_FALLBACK
cfg.tool_scopes = {"add_numbers": ["read"], "get_time": ["read"]}
cfg.tool_inventory_provider = lambda: [
    ManifestTool(
        name="add_numbers",
        description="Add two integers and return the sum.",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
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

app = FastAPI()

# Fix: register metadata manually to avoid mount_mcp's _request parameter bug
@app.get(build_resource_metadata_path(cfg.resource_uri))
async def metadata_endpoint(request: Request):
    body, headers = metadata_json_response(cfg)
    return Response(content=body, media_type="application/json", headers=headers)

# mount_mcp wraps mcp_handler with token validation
mount_mcp(app, "/mcp", mcp_handler, cfg)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
