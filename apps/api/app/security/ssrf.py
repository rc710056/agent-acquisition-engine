import socket
import ipaddress
from urllib.parse import urlparse
from typing import Tuple, List, Optional

BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 Private
    ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918 Private
    ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918 Private
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local / Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("0.0.0.0/8"),        # Current network
    ipaddress.ip_network("100.64.0.0/10"),    # Carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),     # IETF Protocol Assignments
    ipaddress.ip_network("198.18.0.0/15"),    # Benchmarking
    ipaddress.ip_network("224.0.0.0/4"),      # Multicast
    ipaddress.ip_network("240.0.0.0/4"),      # Reserved
    ipaddress.ip_network("::1/128"),          # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 Unique Local Address
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
]

class SSRFValidator:
    """
    Validates target URLs against Server-Side Request Forgery (SSRF) vulnerabilities.
    Enforces protocol whitelists, domain resolution verification, and private IP blocking.
    """

    ALLOWED_SCHEMES = {"http", "https"}

    @classmethod
    def validate_url(cls, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validates URL scheme, structure, and hostname against SSRF targets.
        Returns (is_safe, error_reason).
        """
        if not url:
            return False, "URL cannot be empty."

        try:
            parsed = urlparse(url)
        except Exception as e:
            return False, f"Malformed URL: {str(e)}"

        if parsed.scheme.lower() not in cls.ALLOWED_SCHEMES:
            return False, f"Unsupported scheme '{parsed.scheme}'. Only http and https are permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "URL is missing a valid hostname."

        # Check raw IP or resolve domain
        is_safe, reason = cls.resolve_and_validate_host(hostname, parsed.port)
        if not is_safe:
            return False, reason

        return True, None

    @classmethod
    def resolve_and_validate_host(cls, hostname: str, port: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """
        Resolves hostname via DNS and verifies that no resulting IP addresses
        fall into private, loopback, or metadata network ranges.
        """
        # Block literal localhost keywords
        lower_host = hostname.lower()
        if lower_host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
            return False, f"Direct access to '{hostname}' is prohibited (SSRF defense)."

        # Try parsing as raw IP first
        try:
            raw_ip = ipaddress.ip_address(hostname)
            return cls._is_ip_allowed(raw_ip)
        except ValueError:
            pass  # It's a hostname, proceed to DNS resolution

        # Resolve hostname
        try:
            addr_info = socket.getaddrinfo(hostname, port or 80, proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            return False, f"DNS resolution failed for hostname '{hostname}': {str(e)}"
        except Exception as e:
            return False, f"Error resolving hostname '{hostname}': {str(e)}"

        if not addr_info:
            return False, f"No IP addresses resolved for hostname '{hostname}'."

        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                is_allowed, reason = cls._is_ip_allowed(ip)
                if not is_allowed:
                    return False, f"Hostname '{hostname}' resolved to prohibited IP {ip_str}: {reason}"
            except ValueError:
                return False, f"Resolved invalid IP address '{ip_str}'."

        return True, None

    @classmethod
    def _is_ip_allowed(cls, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> Tuple[bool, Optional[str]]:
        if ip.is_loopback:
            return False, "Loopback addresses are forbidden."
        if ip.is_private:
            return False, "Private/internal RFC-1918 network addresses are forbidden."
        if ip.is_link_local:
            return False, "Link-local / cloud metadata addresses (169.254.x.x) are forbidden."
        if ip.is_reserved:
            return False, "Reserved IP space is forbidden."
        if ip.is_multicast:
            return False, "Multicast addresses are forbidden."

        for blocked in BLOCKED_NETWORKS:
            if ip in blocked:
                return False, f"IP belongs to blocked network range {blocked}."

        return True, None
