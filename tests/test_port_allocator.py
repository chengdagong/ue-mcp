"""
Unit tests for port_allocator module.
"""

import socket

import pytest

from ue_mcp.port_allocator import (
    PORT_RANGE_END,
    PORT_RANGE_START,
    _is_port_available,
    find_available_port,
)


class TestPortAvailability:
    """Tests for port availability checking."""

    def test_free_port_is_available(self):
        """A port that is not bound should be available."""
        # Use a port in our range that is likely free
        port = PORT_RANGE_START + 50
        # First check it's available
        assert _is_port_available(port) is True

    def test_bound_port_is_not_available(self):
        """A port that is bound should not be available."""
        # First find an available port, then bind to it
        port = find_available_port()
        assert _is_port_available(port) is True

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.bind(("0.0.0.0", port))

        try:
            assert _is_port_available(port) is False
        finally:
            sock.close()


class TestFindAvailablePort:
    """Tests for find_available_port function."""

    def test_find_available_port_returns_port_in_range(self):
        """find_available_port should return a port within the configured range."""
        port = find_available_port()
        assert PORT_RANGE_START <= port <= PORT_RANGE_END

    def test_find_available_port_skips_occupied_port(self):
        """find_available_port should skip ports that are already in use."""
        # First find an available port, then occupy it
        first_port = find_available_port()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.bind(("0.0.0.0", first_port))

        try:
            # Now find another port - it should be different
            second_port = find_available_port()
            assert second_port != first_port
        finally:
            sock.close()

    def test_find_available_port_multiple_calls_different_ports(self):
        """Multiple calls should return different ports when previous ones are occupied."""
        sockets = []
        ports = []

        try:
            # Allocate multiple ports
            for _ in range(3):
                port = find_available_port()
                # Bind to it to simulate it being occupied
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.bind(("0.0.0.0", port))
                sockets.append(sock)
                ports.append(port)

            # All ports should be unique
            assert len(set(ports)) == 3
        finally:
            for sock in sockets:
                sock.close()

    def test_find_available_port_custom_range(self):
        """find_available_port should respect custom range parameters."""
        custom_start = 7000
        custom_end = 7010

        port = find_available_port(start=custom_start, end=custom_end)
        assert custom_start <= port <= custom_end
