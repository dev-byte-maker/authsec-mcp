from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from starlette.routing import Route
import datetime
from datetime import timezone
from dotenv import load_dotenv
from authsec_sdk import from_env, mount_mcp, ManifestTool

load_dotenv()

mcp = FastMCP("Simple MCP Server")

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    return a + b

@mcp.tool()
def get_time() -> str:
    return datetime.datetime.now(timezone.utc).isoformat()

def my_tools() -> list[ManifestTool]:
    return [
        ManifestTool(
            name="add_numbers",
            description="Add two integers and return their sum",
            input_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            suggested_scopes=["math:read"],
        ),
        ManifestTool(
            name="get_time",
            description="Return the current UTC time in ISO 8601 format",
            input_schema={"type": "object", "properties": {}},
            suggested_scopes=["time:read"],
        ),
    ]

cfg = from_env()
cfg.tool_inventory_provider = my_tools
cfg.publish_manifest=True

app = FastAPI()

mcp_app = mcp.streamable_http_app()


mount_mcp(app, "/mcp", mcp_app, cfg)
