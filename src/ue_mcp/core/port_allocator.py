"""
UE-MCP Port Allocator

Dynamic multicast port allocation for multiple UE5 editor instances.
"""

import logging
import socket

logger = logging.getLogger(__name__)

PORT_RANGE_START = 6767
PORT_RANGE_END = 6866


def find_available_port(start: int = PORT_RANGE_START, end: int = PORT_RANGE_END) -> int:
    """
    Find an available UDP port for multicast binding.

    Scans the port range to find a port not currently in use.

    Args:
        start: Start of port range (inclusive)
        end: End of port range (inclusive)

    Returns:
        Available port number

    Raises:
        RuntimeError: If no available port found (practically impossible)
    """
    for port in range(start, end + 1):
        if _is_port_available(port):
            logger.info(f"Found available multicast port: {port}")
            return port

    raise RuntimeError(f"No available port in range {start}-{end}")


def _is_port_available(port: int) -> bool:
    """
    Check if a UDP port is available for binding.

    Args:
        port: Port number to check

    Returns:
        True if port is available, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(0.1)
        sock.bind(("0.0.0.0", port))
        sock.close()
        return True
    except OSError:
        return False
