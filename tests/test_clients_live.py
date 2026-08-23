"""Exercise NpmClient/ProxmoxClient against a tiny local fake HTTP server,
so the actual request/parsing code paths (not just merge logic) get run."""
import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.npm import NpmClient
from app.clients.proxmox import ProxmoxClient

npm_login_calls = 0


class FakeHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        global npm_login_calls
        if self.path == "/api/tokens":
            npm_login_calls += 1
            self._send_json({"token": f"faketoken{npm_login_calls}", "expires": "2099-01-01T00:00:00.000Z"})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_GET(self):
        auth = self.headers.get("Authorization", "")

        if self.path.startswith("/api/nginx/proxy-hosts"):
            if auth != "Bearer faketoken1":
                self._send_json({"error": "unauthorized"}, 401)
                return
            self._send_json(
                [
                    {
                        "id": 1,
                        "domain_names": ["svc.example.com"],
                        "forward_scheme": "http",
                        "forward_host": "10.0.0.9",
                        "forward_port": 8080,
                        "enabled": 1,
                        "certificate_id": 5,
                        "meta": {"nginx_online": True},
                    }
                ]
            )
            return

        if self.path == "/api2/json/nodes":
            self._send_json({"data": [{"node": "pve"}]})
            return
        if self.path == "/api2/json/nodes/pve/qemu":
            self._send_json({"data": [{"vmid": 100, "name": "test-vm", "status": "running", "cpu": 0.1, "mem": 111, "maxmem": 222}]})
            return
        if self.path == "/api2/json/nodes/pve/lxc":
            self._send_json({"data": []})
            return
        if self.path == "/api2/json/nodes/pve/qemu/100/agent/network-get-interfaces":
            self._send_json(
                {
                    "data": {
                        "result": [
                            {"ip-addresses": [{"ip-address-type": "ipv4", "ip-address": "127.0.0.1"}]},
                            {"ip-addresses": [{"ip-address-type": "ipv4", "ip-address": "10.0.0.9"}]},
                        ]
                    }
                }
            )
            return
        self._send_json({"error": "not found"}, 404)


def run_server():
    server = HTTPServer(("127.0.0.1", 0), FakeHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


async def main():
    server, port = run_server()
    base = f"http://127.0.0.1:{port}"

    npm = NpmClient(base, "a@b.com", "secret", verify_ssl=False)
    hosts = await npm.list_proxy_hosts()
    assert len(hosts) == 1, hosts
    assert hosts[0].primary_domain == "svc.example.com"
    assert hosts[0].href == "https://svc.example.com"
    assert hosts[0].forward_host == "10.0.0.9"
    assert npm_login_calls == 1, "should log in exactly once and reuse the token"

    px = ProxmoxClient(base, "root@pam!dashboard", "secret", verify_ssl=False)
    guests = await px.list_guests()
    assert len(guests) == 1, guests
    g = guests[0]
    assert g.name == "test-vm"
    assert g.status == "running"
    assert g.ip_addresses == ["10.0.0.9"], g.ip_addresses  # loopback filtered out

    server.shutdown()
    print("All live-client tests passed.")


asyncio.run(main())
