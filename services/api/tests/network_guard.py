"""The test network guard. Installed for the whole pytest session by conftest.py: a DNS lookup
or a socket connection to any host but loopback raises OutboundRequestError and is recorded.
conftest fails any test that leaves a recorded attempt, so swallowing the error does not hide
it. Only a test marked live, run with LIVE=1, has the guard lifted."""

import ipaddress
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class OutboundRequestError(OSError):
    """A test tried to reach the network without LIVE=1."""


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo
_attempts: list[str] = []


def _name(host: object) -> str | None:
    if host is None:
        return None
    return host.decode() if isinstance(host, bytes) else str(host)


def _ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return None


def _is_local(host: object) -> bool:
    name = _name(host)
    if name is None or name == "localhost":
        return True
    ip = _ip(name)
    return ip is not None and ip.is_loopback


def _refuse(what: str) -> None:
    _attempts.append(what)
    raise OutboundRequestError(f"no network in tests without LIVE=1: {what}")


def _check(sock: socket.socket, address: Any) -> None:
    inet = sock.family in (socket.AF_INET, socket.AF_INET6)
    if inet and not _is_local(address[0]):
        _refuse(f"connect {address[0]}:{address[1]}")


def _connect(self: socket.socket, address: Any) -> None:
    _check(self, address)
    _real_connect(self, address)


def _connect_ex(self: socket.socket, address: Any) -> int:
    _check(self, address)
    return _real_connect_ex(self, address)


def _getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    """An IP literal resolves without the network; its connect is checked instead."""
    name = _name(host)
    if not _is_local(host) and name is not None and _ip(name) is None:
        _refuse(f"resolve {name}")
    return _real_getaddrinfo(host, *args, **kwargs)


def install() -> None:
    socket.socket.connect = _connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = _getaddrinfo


def uninstall() -> None:
    socket.socket.connect = _real_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _real_connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = _real_getaddrinfo


@contextmanager
def lifted() -> Iterator[None]:
    uninstall()
    try:
        yield
    finally:
        install()


def take_attempts() -> list[str]:
    """The attempts recorded since the last call, cleared."""
    out = list(_attempts)
    _attempts.clear()
    return out


def assert_none(attempts: list[str]) -> None:
    assert not attempts, f"outbound requests in a test without LIVE=1: {attempts}"
