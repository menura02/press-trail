"""Direct HTTP transport. Every socket connects to a validated numeric address."""
import http.client
import ipaddress
import re
import socket
import ssl
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import BoundedSemaphore, Timer
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from protego import Protego

AGENT = "HaberIzSurucusu/1.0"
MAX_BYTES = 2 * 1024 * 1024
REDIRECTS = {301, 302, 303, 307, 308}
DNS_POOL = ThreadPoolExecutor(max_workers=4)
DNS_SLOTS = BoundedSemaphore(4)
SPECIAL_V4 = tuple(map(ipaddress.ip_network, ("192.0.0.0/24", "192.88.99.0/24")))
GLOBAL_V6 = ipaddress.ip_network("2000::/3")
SPECIAL_V6 = tuple(map(ipaddress.ip_network, ("2001::/23", "2002::/16", "3fff::/20")))


class FetchError(Exception):
    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


def normalize_url(raw, base=None):
    try:
        if not raw or len(raw) > 2000 or re.search(r"[\x00-\x20\x7f\\]", raw):
            raise ValueError
        u = urlsplit(urljoin(base, raw) if base else raw)
        if u.scheme not in ("http", "https") or not u.hostname or u.username is not None:
            raise ValueError
        port = 443 if u.scheme == "https" else 80
        if u.port not in (None, port) or "%" in u.hostname:
            raise ValueError
        host = u.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        if not host or not re.fullmatch(r"[a-z0-9.:-]+", host):
            raise ValueError
        normalized = urlunsplit((u.scheme, f"[{host}]" if ":" in host else host,
                           quote(u.path or "/", safe="/:@!$&'()*+,;=-._~%"),
                           quote(u.query, safe="/?:@!$&'()*+,;=-._~%"), ""))
        if len(normalized) > 2000:
            raise ValueError
        return normalized
    except (ValueError, UnicodeError):
        raise FetchError("blocked_target") from None


def public_address(host, port):
    if not DNS_SLOTS.acquire(timeout=5):
        raise FetchError("timeout")
    future = DNS_POOL.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    future.add_done_callback(lambda _: DNS_SLOTS.release())
    try:
        rows = future.result(timeout=5)
        if not rows:
            raise FetchError("dns")
        addresses = [ipaddress.ip_address(row[4][0]) for row in rows]
        for ip in addresses:
            if (not ip.is_global or ip.is_multicast or ip.is_reserved
                    or (ip.version == 4 and any(ip in net for net in SPECIAL_V4))
                    or (ip.version == 6 and
                        (ip not in GLOBAL_V6 or any(ip in net for net in SPECIAL_V6)))):
                raise FetchError("blocked_target")
        return addresses[0]
    except socket.gaierror:
        raise FetchError("dns") from None
    except TimeoutError:
        raise FetchError("timeout") from None


def dial(ip, port, timeout):
    family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect((str(ip), port))
        return sock
    except BaseException:
        sock.close()
        raise


@dataclass
class Response:
    url: str
    status: int
    headers: dict
    body: bytes


class Client:
    def __init__(self):
        self.last_request = {}
        self.robots = {}

    def _pace(self, host, delay):
        host = host.rstrip(".")
        remaining = self.last_request.get(host, 0) + delay - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        self.last_request[host] = time.monotonic()

    def _request(self, url, headers, delay):
        u = urlsplit(url)
        port = 443 if u.scheme == "https" else 80
        ip = public_address(u.hostname, port)
        self._pace(u.hostname, delay)
        conn = http.client.HTTPConnection(u.hostname, port, timeout=5)
        transport = None
        response = None

        def connect():
            nonlocal transport
            transport = conn.sock = dial(ip, port, 5)
            if u.scheme == "https":
                transport = conn.sock = ssl.create_default_context().wrap_socket(
                    conn.sock, server_hostname=u.hostname, do_handshake_on_connect=False)
                transport.do_handshake()

        conn.connect = connect
        deadline = time.monotonic() + 15

        def interrupt():
            if transport is not None:
                try:
                    transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        watchdog = Timer(15, interrupt)
        watchdog.daemon = True
        watchdog.start()
        try:
            target = u.path + ("?" + u.query if u.query else "")
            conn.request("GET", target, headers={"User-Agent": AGENT,
                         "Accept-Encoding": "gzip", "Connection": "close", **headers})
            res = response = conn.getresponse()
            response_headers = {k.lower(): v for k, v in res.getheaders()}
            if res.status in REDIRECTS or res.status == 304 or res.status >= 400:
                return Response(url, res.status, response_headers, b"")
            encoding = response_headers.get("content-encoding", "identity").lower()
            if encoding not in {"gzip", "identity"}:
                raise FetchError("encoding")
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
            received = 0
            body = bytearray()
            while chunk := res.read1(16384):
                if time.monotonic() > deadline:
                    raise FetchError("timeout")
                received += len(chunk)
                if received > MAX_BYTES:
                    raise FetchError("too_large")
                body.extend(decoder.decompress(chunk, MAX_BYTES + 1 - len(body)) if decoder else chunk)
                if len(body) > MAX_BYTES or (decoder and decoder.unused_data):
                    raise FetchError("too_large" if len(body) > MAX_BYTES else "encoding")
            if time.monotonic() > deadline:
                raise FetchError("timeout")
            if res.length:
                raise FetchError("transport")
            if decoder and not decoder.eof:
                raise FetchError("encoding")
            return Response(url, res.status, response_headers, bytes(body))
        except TimeoutError:
            raise FetchError("timeout") from None
        except (OSError, http.client.HTTPException, zlib.error, ValueError):
            raise FetchError("timeout" if time.monotonic() >= deadline else "transport") from None
        finally:
            watchdog.cancel()
            if response is not None:
                response.close()
            conn.close()

    def _policy(self, url):
        u = urlsplit(url)
        origin = f"{u.scheme}://{u.netloc}"
        cached = self.robots.get(origin)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        res = self.get(origin + "/robots.txt", check_robots=False)
        if res.status == 200:
            robots = Protego.parse(res.body.decode("utf-8-sig", errors="replace"))
        elif res.status in (404, 410):
            robots = Protego.parse("")
        else:
            raise FetchError("robots")
        self.robots[origin] = (time.monotonic() + 900, robots)
        return robots

    def get(self, url, headers=None, check_robots=True):
        url = normalize_url(url)
        for _ in range(6):
            delay = 1.0
            if check_robots:
                policy = self._policy(url)
                if not policy.can_fetch(url, AGENT):
                    raise FetchError("robots")
                delay = max(delay, policy.crawl_delay(AGENT) or 0)
                rate = policy.request_rate(AGENT)
                if rate and rate.requests > 0:
                    delay = max(delay, rate.seconds / rate.requests)
                if delay > 30:
                    raise FetchError("robots")
            response = self._request(url, headers or {}, delay)
            if response.status not in REDIRECTS:
                return response
            url = normalize_url(response.headers.get("location"), url)
            headers = {}
        raise FetchError("redirect_limit")

