"""Standalone fake NPM+Proxmox server for a manual visual smoke test."""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9999


class FakeHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/api/tokens":
            self._json({"token": "faketoken", "expires": "2099-01-01T00:00:00.000Z"})
        else:
            self._json({}, 404)

    def do_GET(self):
        if self.path.startswith("/api/nginx/proxy-hosts"):
            self._json(
                [
                    {
                        "id": 1,
                        "domain_names": ["karakeep.provider.example"],
                        "forward_scheme": "http",
                        "forward_host": "10.0.0.5",
                        "forward_port": 3000,
                        "enabled": 1,
                        "certificate_id": 1,
                        "meta": {"nginx_online": True},
                    },
                    {
                        "id": 2,
                        "domain_names": ["auth.provider.example"],
                        "forward_scheme": "http",
                        "forward_host": "authentik_server",
                        "forward_port": 9000,
                        "enabled": 1,
                        "certificate_id": 1,
                        "meta": {"nginx_online": True},
                    },
                    {
                        "id": 3,
                        "domain_names": ["old-project.provider.example"],
                        "forward_scheme": "http",
                        "forward_host": "10.0.0.9",
                        "forward_port": 80,
                        "enabled": 1,
                        "certificate_id": None,
                        "meta": {"nginx_online": False},
                    },
                ]
            )
        elif self.path == "/api2/json/nodes":
            self._json({"data": [{"node": "pve"}]})
        elif self.path == "/api2/json/nodes/pve/qemu":
            self._json(
                {
                    "data": [
                        {"vmid": 100, "name": "authentik-vm", "status": "running", "cpu": 0.12, "mem": 512_000_000, "maxmem": 2_000_000_000},
                        {"vmid": 103, "name": "unused-test-vm", "status": "stopped", "cpu": 0, "mem": 0, "maxmem": 1_000_000_000},
                    ]
                }
            )
        elif self.path == "/api2/json/nodes/pve/lxc":
            self._json(
                {
                    "data": [
                        {"vmid": 101, "name": "karakeep-lxc", "status": "running", "cpu": 0.03, "mem": 180_000_000, "maxmem": 1_000_000_000},
                    ]
                }
            )
        elif self.path == "/api2/json/nodes/pve/qemu/100/agent/network-get-interfaces":
            self._json({"data": {"result": []}})  # simulate: no guest agent -> unmatched
        elif self.path == "/api2/json/nodes/pve/lxc/101/interfaces":
            self._json({"data": [{"name": "eth0", "inet": "10.0.0.5/24"}]})
        else:
            self._json({}, 404)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), FakeHandler).serve_forever()
