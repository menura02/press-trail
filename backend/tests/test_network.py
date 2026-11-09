import gzip
import io
import ipaddress

import pytest

from app import network
from app.network import Client, FetchError, Response, normalize_url, public_address


def address(ip):
    return [(network.socket.AF_INET6 if ":" in ip else network.socket.AF_INET,
             network.socket.SOCK_STREAM, 6, "", (ip, 80))]


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.2",
                                "224.0.0.1", "192.0.0.50", "192.88.99.1", "::1", "fc00::1", "fe80::1",
                                "::ffff:8.8.8.8", "64:ff9b::a00:1", "3fff::1"])
def test_blocks_non_public(monkeypatch, ip):
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *a, **k: address(ip))
    with pytest.raises(FetchError, match="blocked_target"):
        public_address("target.example", 80)


@pytest.mark.parametrize("url", ["file:///a", "https://u:p@domain.test/", "http://domain.test:443/",
                                 "https://domain.test:8443/", "http://[fe80::1%25eth0]/",
                                 "http://good.test\\@evil.test/"])
def test_blocks_unsafe_url(url):
    with pytest.raises(FetchError, match="blocked_target"):
        normalize_url(url)


def test_preserves_query():
    assert normalize_url("HTTPS://EXAMPLE.COM:443/x?ref=1&id=2&id=3#top") == (
        "https://example.com/x?ref=1&id=2&id=3")


class FakeSocket:
    def __init__(self, data):
        self.data = data
        self.request = b""

    def sendall(self, data):
        self.request += data

    def makefile(self, *_):
        return io.BytesIO(self.data)

    def close(self):
        pass


def test_rebinding_and_environment_proxy(monkeypatch):
    calls = []
    sock = FakeSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    def resolve(host, *_a, **_kw):
        calls.append(host)
        return address("93.184.216.34" if len(calls) == 1 else "127.0.0.1")

    def dial(ip, port, timeout):
        assert ip == ipaddress.ip_address("93.184.216.34") and port == 80
        return sock

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9999")
    monkeypatch.setattr(network.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(network, "dial", dial)
    assert Client().get("http://target.example/data", check_robots=False).body == b"ok"
    assert calls == ["target.example"]
    assert b"GET /data HTTP/1.1" in sock.request and b"Host: target.example" in sock.request


@pytest.mark.parametrize("robots", [True, False])
def test_redirect_is_checked_before_dial(monkeypatch, robots):
    requests = []
    payload = b"HTTP/1.1 302 Found\r\nLocation: http://private.example/a\r\n\r\n"
    def resolve(host, *_a, **_kw):
        return address("10.1.0.1" if host == "private.example" else "93.184.216.34")
    def dial(ip, *_):
        requests.append(str(ip))
        return FakeSocket(payload)
    monkeypatch.setattr(network.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(network, "dial", dial)
    with pytest.raises(FetchError, match="blocked_target"):
        Client().get("http://target.example/data", check_robots=robots)
    assert requests == ["93.184.216.34"]


def test_robots_path_rule(monkeypatch):
    client = Client()
    def request(url, headers, delay):
        assert url.endswith("/robots.txt")
        return Response(url, 200, {}, b"User-agent: *\nDisallow: /private/*.html$\n")
    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(FetchError, match="robots"):
        client.get("https://target.example/private/story.html")


def test_gzip_decoded_size_limit(monkeypatch):
    body = gzip.compress(b"x" * 4096)
    raw = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n\r\n" + body
    monkeypatch.setattr(network, "MAX_BYTES", 100)
    monkeypatch.setattr(network.socket, "getaddrinfo", lambda *a, **k: address("93.184.216.34"))
    monkeypatch.setattr(network, "dial", lambda *_: FakeSocket(raw))
    with pytest.raises(FetchError, match="too_large"):
        Client().get("http://target.example/data", check_robots=False)

