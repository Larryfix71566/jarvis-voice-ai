"""Read-only synthetic graph for desktop acceptance; offline test VM only.

Run as mortimer-dev. Bind only 127.0.0.1:7861; fail if occupied. No vault,
credentials, external calls, or mutation endpoints. Stop the process after use.
Optional worker-owned mode.json selects normal/error/invalid/empty responses.
Request logs contain paths and modes only, never headers or credentials.
"""
import json
import os
from pathlib import Path
import subprocess
from socketserver import TCPServer
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


def graph(query):
    nodes, edges = [], []
    for group in range(5):
        prefix, turn = f"prefix:project.{group}", f"turn:{group}"
        nodes.extend([
            {"id": prefix, "type": "prefix", "label": f"Synthetic project {group}", "attrs": {}},
            {"id": turn, "type": "turn", "label": f"Synthetic conversation {group}", "attrs": {"role": "user"}},
        ])
        for item in range(8):
            key = f"fact:project.{group}.item.{item}"
            nodes.append({"id": key, "type": "fact", "label": f"Synthetic memory {group}.{item}",
                          "attrs": {"provenance": "Synthetic desktop acceptance fixture",
                                    "content_preview": "Fixture text only; no private memory data."}})
            edges.extend([
                {"from": key, "to": prefix, "type": "child_of", "attrs": {"fixture": True}},
                {"from": key, "to": turn, "type": "stated_in", "attrs": {"fixture": True}},
            ])
    focus = query.get("focus", [""])[0]
    try:
        depth = min(4, max(1, int(query.get("depth", ["2"])[0])))
    except ValueError:
        depth = 2
    allowed_types = set(query.get("edge_types", [""])[0].split(",")) - {""}
    if allowed_types:
        edges = [edge for edge in edges if edge["type"] in allowed_types]
    if focus:
        found = next((node["id"] for node in nodes
                      if node["id"] == focus or node["label"].casefold() == focus.casefold()), None)
        reached = {found} if found else set()
        for _ in range(depth):
            reached |= {end for edge in edges if edge["from"] in reached or edge["to"] in reached
                        for end in (edge["from"], edge["to"])}
        nodes = [node for node in nodes if node["id"] in reached]
        edges = [edge for edge in edges if edge["from"] in reached and edge["to"] in reached]
        focus = found or focus
    return {"ok": True, "graph": "memory", "focus": focus or None, "depth": depth,
            "edge_types": sorted(allowed_types or {"child_of", "stated_in"}),
            "node_count": len(nodes), "edge_count": len(edges), "truncated": False,
            "truncated_reason": "", "nodes": nodes, "edges": edges,
            "legend": {"node_types": {"fact": "#5ec8ff", "prefix": "#a78bfa", "turn": "#9aa5b1"},
                       "edge_types": {"child_of": "solid", "stated_in": "dashed"}}}


def main():
    print("Starting VM-only synthetic graph fixture", flush=True)
    if os.getuid() != 502 or subprocess.check_output(
            ["/usr/sbin/sysctl", "-n", "kern.hv_vmm_present"], text=True).strip() != "1":
        raise SystemExit("This fixture runs only as the disposable VM worker.")
    root = Path("/Users/mortimer-dev/graph-acceptance")
    root.mkdir(mode=0o700, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if len(self.path) > 2048:
                self.send_error(414)
                return
            url = urlsplit(self.path)
            mode_file = root / "mode.json"
            mode = json.loads(mode_file.read_text()).get("mode", "normal") if mode_file.exists() else "normal"
            with (root / "requests.jsonl").open("a") as log:
                log.write(json.dumps({"path": self.path, "mode": mode}) + "\n")
            status = 200
            if url.path == "/api/graph/memory":
                body = graph(parse_qs(url.query))
                if mode == "error":
                    status, body = 503, {"ok": False, "error": "Synthetic fixture unavailable"}
                elif mode == "invalid":
                    body["graph"] = "unsupported-synthetic-schema"
                elif mode == "empty":
                    body.update(nodes=[], edges=[], node_count=0, edge_count=0)
            elif url.path == "/api/health":
                body = {"ok": True, "fixture": True}
            else:
                status, body = 404, {"ok": False, "error": "Route not supplied by synthetic graph fixture"}
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            self.send_error(405, "Read-only acceptance fixture")

        do_PUT = do_PATCH = do_DELETE = do_POST

    class LoopbackServer(ThreadingHTTPServer):
        def server_bind(self):
            # HTTPServer normally reverse-resolves its address here. The test
            # server has a fixed loopback identity and must not depend on DNS.
            TCPServer.server_bind(self)
            self.server_name = "localhost"
            self.server_port = self.server_address[1]

    server = LoopbackServer(("127.0.0.1", 7861), Handler)
    print("Synthetic graph fixture listening on VM loopback only", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
