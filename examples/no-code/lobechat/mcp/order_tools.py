"""Test-only MCP server (Streamable HTTP) with two order tools for the LobeHub E2E.

LobeHub's server agent runtime calls remote MCP servers over HTTP, so the E2E adds this server
as a custom MCP plugin and asks the agent to use it:

  get_order_status(order_id)  returns a fixed status record for the order
  cancel_order(order_id)      always fails, to produce a failing tool call

Run:  python order_tools.py            (listens on 127.0.0.1:8790, path /mcp)
Env:  ORDER_TOOLS_HOST, ORDER_TOOLS_PORT, ORDER_TOOLS_ALLOWED_HOSTS (comma list, DNS rebinding check)
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

HOST = os.environ.get("ORDER_TOOLS_HOST", "127.0.0.1")
PORT = int(os.environ.get("ORDER_TOOLS_PORT", "8790"))
ALLOWED = [h.strip() for h in os.environ.get(
    "ORDER_TOOLS_ALLOWED_HOSTS", f"127.0.0.1:{PORT},localhost:{PORT},host.docker.internal:{PORT}"
).split(",") if h.strip()]

mcp = FastMCP(
    "order-tools",
    host=HOST,
    port=PORT,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=ALLOWED, allowed_origins=[]
    ),
)


def order_status(order_id: str) -> dict:
    """Pure function behind get_order_status (unit-tested)."""
    order_id = order_id.strip()
    return {
        "order_id": order_id,
        "status": "shipped",
        "carrier": "ParcelCo",
        "eta_days": 2,
        "note": f"tracking ref TRK-{order_id[-6:].upper()}",
    }


@mcp.tool()
def get_order_status(order_id: str) -> dict:
    """Look up the shipping status of an order by its order id."""
    return order_status(order_id)


class CancelRefused(RuntimeError):
    pass


@mcp.tool()
def cancel_order(order_id: str) -> str:
    """Cancel an order by its order id."""
    raise CancelRefused(f"cancel refused for {order_id.strip()}: order already shipped")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
