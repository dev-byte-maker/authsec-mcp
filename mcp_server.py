from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import Response
from mcp.server.fastmcp import FastMCP
from authsec_sdk import (
    Runtime, from_env,
    TokenInvalidError, TokenInactiveError,
    InsufficientScopeError, PolicyUnavailableError,
)
from authsec_sdk.runtime.metadata import (
    build_resource_metadata_path,
    metadata_json_response,
    build_www_authenticate,
)
import json
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


# ── AuthSec runtime (module-level so Railway can also use uvicorn mcp_server:app) ──

cfg = from_env()
rt = Runtime(cfg)


# ── ASGI middleware ──────────────────────────────────────────────────────────

class AuthSecMiddleware:
    """Validates bearer tokens and enforces tool policy for /mcp requests."""

    def __init__(self, app, runtime: Runtime):
        self.app = app
        self.rt = runtime

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path", "") != "/mcp":
            await self.app(scope, receive, send)
            return

        headers = {k: v for k, v in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode()
        parts = auth.split(None, 1)

        if len(parts) != 2 or parts[0].lower() != "bearer":
            await self._send_error(send, 401, "invalid_token", "missing bearer token")
            return

        try:
            principal = await self.rt.validate_token(parts[1].strip())
        except (TokenInvalidError, TokenInactiveError) as e:
            await self._send_error(send, 401, "invalid_token", str(e))
            return
        except Exception:
            await self._send_error(send, 401, "invalid_token", "token validation failure")
            return

        scope.setdefault("state", {})["authsec_principal"] = principal

        if scope["method"] == "POST":
            first = await receive()
            body = first.get("body", b"")
            more = first.get("more_body", False)

            try:
                payload = json.loads(body)
                if isinstance(payload, dict) and payload.get("method") == "tools/call":
                    tool_name = (payload.get("params") or {}).get("name", "")
                    if tool_name:
                        await self.rt.authorize_tool(principal, tool_name)
            except InsufficientScopeError as e:
                await self._send_insufficient_scope(send, e)
                return
            except PolicyUnavailableError as e:
                await self._send_error(send, 503, "policy_unavailable", str(e))
                return
            except Exception:
                pass

            replayed = False

            async def replay_receive():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": more}
                return await receive()

            await self.app(scope, replay_receive, send)
        else:
            await self.app(scope, receive, send)

    async def _send_error(self, send, status: int, error: str, description: str):
        www_auth = build_www_authenticate(self.rt.cfg, error=error, error_description=description)
        body = json.dumps({"error": error, "error_description": description}).encode()
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"),
            (b"www-authenticate", www_auth.encode()),
        ]})
        await send({"type": "http.response.body", "body": body})

    async def _send_insufficient_scope(self, send, err: InsufficientScopeError):
        www_auth = build_www_authenticate(
            self.rt.cfg, error="insufficient_scope",
            error_description=f"tool {err.tool!r} requires {err.required!r}",
            scope=" ".join(err.required),
        )
        body = json.dumps({
            "error": "insufficient_scope",
            "error_description": f"tool {err.tool!r} requires one of {err.required!r}",
            "tool": err.tool,
            "required_scopes": err.required,
        }).encode()
        await send({"type": "http.response.start", "status": 403, "headers": [
            (b"content-type", b"application/json"),
            (b"www-authenticate", www_auth.encode()),
        ]})
        await send({"type": "http.response.body", "body": body})


# ── FastAPI app ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await rt.startup()
    except Exception as e:
        print(f"[authsec] startup warning (non-fatal): {e}")
    yield


app = FastAPI(lifespan=lifespan)

# RFC 9728 metadata — must be registered before the root mount
@app.get(build_resource_metadata_path(cfg.resource_uri))
async def metadata_endpoint():
    body, headers = metadata_json_response(rt.cfg)
    return Response(content=body, media_type="application/json", headers=headers)

# Mount MCP app at root so the path is NOT stripped — MCP handles /mcp internally
app.mount("/", AuthSecMiddleware(mcp.streamable_http_app(), rt))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
