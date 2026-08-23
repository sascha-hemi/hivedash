"""Sanity tests for the merge logic - no network involved."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.npm import ProxyHost
from app.clients.proxmox import Guest
from app.merge import build_dashboard


def test_match_by_ip():
    host = ProxyHost(
        id=1,
        domain_names=["karakeep.provider.example"],
        forward_scheme="http",
        forward_host="10.0.0.5",
        forward_port=3000,
        enabled=True,
        online=True,
        ssl=True,
    )
    guest = Guest(
        vmid=101,
        name="karakeep-lxc",
        node="pve",
        kind="lxc",
        status="running",
        cpu=0.05,
        mem=200_000_000,
        maxmem=1_000_000_000,
        ip_addresses=["10.0.0.5"],
    )
    result = build_dashboard([host], [guest], None, None)

    assert len(result["services"]) == 1
    assert result["services"][0]["name"] == "karakeep.provider.example"
    assert result["services"][0]["href"] == "https://karakeep.provider.example"
    assert result["services"][0]["vm"]["vmid"] == 101
    assert result["services"][0]["vm"]["kind"] == "lxc"
    # matched guest must NOT also show up as a separate infrastructure tile
    assert result["infrastructure"] == []


def test_match_by_hostname_case_insensitive():
    # an admin can point NPM at a guest's hostname instead of its raw IP - Proxmox's "name" field
    # doubles as the actual hostname for the common case of an LXC/VM configured to use it as such.
    host = ProxyHost(
        id=3,
        domain_names=["homarr.provider.example"],
        forward_scheme="http",
        forward_host="Homarr",  # deliberately different casing than the guest's name below
        forward_port=7575,
        enabled=True,
        online=True,
        ssl=True,
    )
    guest = Guest(
        vmid=104,
        name="homarr",
        node="pve",
        kind="lxc",
        status="running",
        cpu=0.01,
        mem=100_000_000,
        maxmem=500_000_000,
        ip_addresses=[],  # no guest-agent IP at all - hostname is the only way to match
    )
    result = build_dashboard([host], [guest], None, None)

    assert result["services"][0]["vm"] is not None
    assert result["services"][0]["vm"]["vmid"] == 104
    assert result["infrastructure"] == []


def test_ip_match_takes_precedence_over_hostname_match():
    # if forward_host happens to equal one guest's IP AND a different guest's name, the IP match
    # wins - IP is the more specific/deliberate signal.
    host = ProxyHost(
        id=4, domain_names=["x.example.com"], forward_scheme="http", forward_host="10.0.0.7",
        forward_port=80, enabled=True, online=True, ssl=False,
    )
    ip_guest = Guest(
        vmid=105, name="ip-guest", node="pve", kind="lxc", status="running",
        cpu=0.0, mem=None, maxmem=None, ip_addresses=["10.0.0.7"],
    )
    name_guest = Guest(
        vmid=106, name="10.0.0.7", node="pve", kind="lxc", status="running",
        cpu=0.0, mem=None, maxmem=None, ip_addresses=[],
    )
    result = build_dashboard([host], [ip_guest, name_guest], None, None)
    assert result["services"][0]["vm"]["vmid"] == 105


def test_unmatched_host_and_guest_both_shown():
    host = ProxyHost(
        id=2,
        domain_names=["auth.provider.example"],
        forward_scheme="http",
        forward_host="app-container",  # docker service name, not an IP -> no match possible
        forward_port=9000,
        enabled=True,
        online=True,
        ssl=True,
    )
    guest = Guest(
        vmid=102,
        name="unrelated-vm",
        node="pve",
        kind="qemu",
        status="stopped",
        cpu=None,
        mem=None,
        maxmem=None,
        ip_addresses=[],  # e.g. guest agent not installed
    )
    result = build_dashboard([host], [guest], None, None)

    assert len(result["services"]) == 1
    assert result["services"][0]["vm"] is None
    assert result["services"][0]["href"] == "https://auth.provider.example"

    assert len(result["infrastructure"]) == 1
    assert result["infrastructure"][0]["name"] == "unrelated-vm"
    assert result["infrastructure"][0]["status"] == "stopped"


def test_errors_propagate_and_empty_lists_dont_crash():
    result = build_dashboard(None, None, "npm down", "proxmox down")
    assert result["services"] == []
    assert result["infrastructure"] == []
    assert result["errors"] == {"npm": "npm down", "proxmox": "proxmox down"}


if __name__ == "__main__":
    test_match_by_ip()
    test_match_by_hostname_case_insensitive()
    test_ip_match_takes_precedence_over_hostname_match()
    test_unmatched_host_and_guest_both_shown()
    test_errors_propagate_and_empty_lists_dont_crash()
    print("All merge tests passed.")
