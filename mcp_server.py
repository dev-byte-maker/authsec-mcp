from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from starlette.routing import Route
import datetime
from datetime import timezone
from dotenv import load_dotenv
from authsec_sdk import from_env, mount_mcp

load_dotenv()

mcp = FastMCP("Simple MCP Server")

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    return a + b

@mcp.tool()
def get_time() -> str:
    return datetime.datetime.now(timezone.utc).isoformat()

cfg = from_env()

app = FastAPI()

mcp_app = mcp.streamable_http_app()


mount_mcp(app, "/mcp", mcp_app, cfg)
