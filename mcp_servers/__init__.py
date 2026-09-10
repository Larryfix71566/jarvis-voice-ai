"""Mortimer MCP services use the repository's locked dependency versions.

GC1 (2026-09-10): FastMCP's startup banner otherwise contacts PyPI before
serving stdio. Offline DNS can block every server for 30 seconds, even
though the HTTP request has a shorter timeout. Update checks belong to
dependency maintenance, not tool startup. Operators may explicitly opt in.
"""
import os

os.environ.setdefault("FASTMCP_CHECK_FOR_UPDATES", "off")
