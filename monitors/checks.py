import ipaddress
import socket
import time
from urllib.parse import urlparse
import httpx

def check_url(target, timeout_seconds=10):
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, None, None, "Only valid HTTP(S) URLs are supported"
    if parsed.username or parsed.password:
        return False, None, None, "Target URLs must not contain a username or password"
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return False, None, None, "Target URL contains an invalid port"
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port)}
        if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
            return False, None, None, "Target resolves to a non-public address"
        start = time.monotonic()
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False, trust_env=False) as client:
            response = client.get(target)
        elapsed = int((time.monotonic() - start) * 1000)
        ok = 200 <= response.status_code < 400
        return ok, response.status_code, elapsed, "" if ok else f"Unexpected HTTP status {response.status_code}"
    except socket.gaierror:
        return False, None, None, "DNS lookup failed"
    except httpx.TimeoutException:
        return False, None, None, "Request timed out"
    except httpx.ConnectError as exc:
        cause = exc
        while cause:
            if isinstance(cause, socket.gaierror):
                return False, None, None, "DNS lookup failed"
            cause = cause.__cause__ or cause.__context__
        return False, None, None, "Could not connect to the target host"
    except httpx.HTTPError as exc:
        return False, None, None, f"HTTP request failed ({type(exc).__name__})"
    except Exception as exc:
        # Avoid storing exception strings that may include credentials, query
        # parameters, or other sensitive parts of the monitored URL.
        return False, None, None, f"Request failed ({type(exc).__name__})"
