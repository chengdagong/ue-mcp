"""
UE-MCP Remote Execution Client

Socket-based communication with UE5 editor for remote Python execution.
Based on UE5's Python Remote Execution protocol.
"""

import json
import logging
import socket
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RemoteExecutionClient:
    """
    Execute commands in UE5 editor via Python Remote Execution (socket-based).

    Requires:
    - Python plugin with remote execution enabled
    - UE5 project with proper configuration
    """

    # Protocol constants
    MAGIC = "ue_py"
    PROTOCOL_VERSION = 1
    SOCKET_TIMEOUT = 0.5
    BUFFER_SIZE = 2_097_152

    class ExecTypes:
        EXECUTE_FILE = "ExecuteFile"
        EXECUTE_STATEMENT = "ExecuteStatement"
        EVALUATE_STATEMENT = "EvaluateStatement"

    def __init__(
        self,
        multicast_group: tuple[str, int] = ("239.0.0.1", 6766),
        multicast_bind_address: str = "0.0.0.0",
        project_name: str = "",
        expected_node_id: Optional[str] = None,
        expected_pid: Optional[int] = None,
    ):
        """
        Initialize RemoteExecutionClient.

        Args:
            multicast_group: Multicast group (ip, port) for discovery
            multicast_bind_address: Address to bind multicast socket
            project_name: Project name to filter UE5 instances
            expected_node_id: If set, only connect to this specific node_id
            expected_pid: If set, verify the editor process ID matches
        """
        self.multicast_group = multicast_group
        self.multicast_bind_address = multicast_bind_address
        self.project_name = project_name
        self.expected_node_id = expected_node_id
        self.expected_pid = expected_pid
        self.unreal_node_id: Optional[str] = None
        self.mcast_sock: Optional[socket.socket] = None
        self.cmd_sock: Optional[socket.socket] = None
        self.cmd_connection: Optional[socket.socket] = None

    def _create_multicast_socket(self) -> socket.socket:
        """Create and configure multicast socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(self.SOCKET_TIMEOUT)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 0)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind((self.multicast_bind_address, self.multicast_group[1]))

        membership = socket.inet_aton(self.multicast_group[0])
        bind_addr = socket.inet_aton(self.multicast_bind_address)
        sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership + bind_addr
        )

        return sock

    def _send_message(self, sock: socket.socket, message: dict[str, Any]) -> None:
        """Send JSON message via socket."""
        data = json.dumps(message).encode()
        sock.sendto(data, self.multicast_group)

    def _receive_all_messages(
        self, sock: socket.socket, message_type: str, timeout: float = 1.0
    ) -> list[dict[str, Any]]:
        """
        Collect ALL responses from multicast socket during timeout window.

        Args:
            sock: Socket to receive from
            message_type: Message type to ignore (our own echo)
            timeout: How long to wait for responses

        Returns:
            List of all discovered instance messages (filtered by project_name and expected_node_id)
        """
        responses: list[dict[str, Any]] = []
        sock.settimeout(0.1)
        start_time = time.time()

        try:
            while time.time() - start_time < timeout:
                try:
                    data, _ = sock.recvfrom(self.BUFFER_SIZE)
                    json_data = json.loads(data.decode("utf-8"))

                    if json_data.get("type") == message_type:
                        continue  # Skip echo

                    node_id = json_data.get("source")

                    # If expected_node_id is set, only accept that specific node
                    if self.expected_node_id and node_id != self.expected_node_id:
                        logger.debug(
                            f"Ignoring node {node_id} (expected {self.expected_node_id})"
                        )
                        continue

                    # Check project name if specified
                    if self.project_name and "data" in json_data:
                        if json_data["data"].get("project_name") != self.project_name:
                            continue

                    # Avoid duplicates by checking node_id
                    if not any(r.get("source") == node_id for r in responses):
                        responses.append(json_data)

                except socket.timeout:
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.debug(f"Error parsing message: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")

        return responses

    def find_unreal_instance(self, timeout: float = 5.0) -> bool:
        """
        Find and connect to running UE5 instance.

        Args:
            timeout: Discovery timeout in seconds

        Returns:
            True if instance found, False otherwise
        """
        try:
            self.mcast_sock = self._create_multicast_socket()

            logger.info("Searching for UE5 instances...")
            if self.project_name:
                logger.info(f"Filter: project_name='{self.project_name}'")

            # Send ping message
            ping_msg = {
                "version": self.PROTOCOL_VERSION,
                "magic": self.MAGIC,
                "source": "ue_mcp",
                "type": "ping",
            }

            self._send_message(self.mcast_sock, ping_msg)

            # Collect all responses
            all_pongs = self._receive_all_messages(
                self.mcast_sock, "ping", timeout=timeout
            )

            if not all_pongs:
                logger.error("No UE5 instances discovered on network")
                return False

            logger.info(f"Discovered {len(all_pongs)} UE5 instance(s):")
            for i, pong in enumerate(all_pongs, 1):
                project = pong.get("data", {}).get("project_name", "Unknown")
                engine = pong.get("data", {}).get("engine_version", "Unknown")
                node_id = pong.get("source", "Unknown")
                logger.info(f"  {i}. {project} (UE {engine}) [node: {node_id}]")

            # Select first instance
            selected = all_pongs[0]
            self.unreal_node_id = selected.get("source")
            project = selected.get("data", {}).get("project_name", "Unknown")
            engine = selected.get("data", {}).get("engine_version", "Unknown")

            if len(all_pongs) > 1:
                logger.warning(
                    f"{len(all_pongs)} instances discovered, selected first match"
                )

            logger.info(
                f"Connecting to: {project} (UE {engine}) [node: {self.unreal_node_id}]"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to find UE5: {e}")
            return False

    def open_connection(self) -> bool:
        """
        Open command connection to UE5.

        Returns:
            True if connection established, False otherwise
        """
        try:
            if not self.unreal_node_id:
                logger.error("Must find UE5 instance first")
                return False

            # Get available port
            with socket.socket() as s:
                s.bind(("", 0))
                cmd_port = s.getsockname()[1]

            # Send open connection message
            open_msg = {
                "type": "open_connection",
                "version": self.PROTOCOL_VERSION,
                "magic": self.MAGIC,
                "source": "ue_mcp",
                "dest": self.unreal_node_id,
                "data": {"command_ip": "127.0.0.1", "command_port": cmd_port},
            }

            self._send_message(self.mcast_sock, open_msg)

            # Create command socket
            self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.cmd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.cmd_sock.bind(("127.0.0.1", cmd_port))
            self.cmd_sock.settimeout(1.0)
            self.cmd_sock.listen()

            self.cmd_connection, _ = self.cmd_sock.accept()
            self.cmd_connection.settimeout(5.0)

            logger.info("Command connection established")
            return True

        except Exception as e:
            logger.error(f"Failed to open connection: {e}")
            return False

    def execute(
        self,
        command: str,
        exec_type: Optional[str] = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Execute Python command in UE5.

        Args:
            command: Python code or file path
            exec_type: ExecTypes.EXECUTE_FILE, EXECUTE_STATEMENT, or EVALUATE_STATEMENT
            timeout: Timeout for command execution

        Returns:
            Dictionary with execution result
        """
        if exec_type is None:
            exec_type = self.ExecTypes.EXECUTE_FILE

        try:
            # Send command message
            cmd_msg = {
                "type": "command",
                "version": self.PROTOCOL_VERSION,
                "magic": self.MAGIC,
                "source": "ue_mcp",
                "dest": self.unreal_node_id,
                "data": {
                    "command": command,
                    "unattended": True,
                    "exec_mode": exec_type,
                },
            }

            data = json.dumps(cmd_msg).encode()
            self.cmd_connection.sendto(data, ("127.0.0.1", 0))

            # Receive result
            self.cmd_connection.settimeout(timeout)
            data_received = b""
            result_data = None

            while True:
                try:
                    recv_data, _ = self.cmd_connection.recvfrom(self.BUFFER_SIZE)
                    data_received += recv_data

                    try:
                        json_data = json.loads(data_received)
                        data_received = b""
                    except json.JSONDecodeError:
                        continue

                    if json_data.get("type") == "command":
                        continue  # Ignore echo

                    result_data = json_data
                    break

                except socket.timeout:
                    break

            if result_data:
                success = result_data.get("data", {}).get("success", False)
                result = result_data.get("data", {}).get("result", "")
                output = result_data.get("data", {}).get("output", [])

                logger.info(f"Command executed: {'Success' if success else 'Failed'}")

                return {
                    "success": success,
                    "result": result,
                    "output": output,
                    "raw": result_data,
                }
            else:
                return {"success": False, "error": "No response from UE5", "output": []}

        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError) as e:
            logger.error(f"Connection lost during command execution: {e}")
            return {"success": False, "error": str(e), "crashed": True, "output": []}
        except OSError as e:
            if "connection" in str(e).lower() or "broken pipe" in str(e).lower():
                logger.error(f"Connection lost during command execution: {e}")
                return {"success": False, "error": str(e), "crashed": True, "output": []}
            else:
                logger.error(f"Command execution failed: {e}")
                return {"success": False, "error": str(e), "crashed": False, "output": []}
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {"success": False, "error": str(e), "crashed": False, "output": []}

    def close_connection(self) -> None:
        """Close connection to UE5."""
        try:
            if self.unreal_node_id and self.mcast_sock:
                close_msg = {
                    "type": "close_connection",
                    "version": self.PROTOCOL_VERSION,
                    "magic": self.MAGIC,
                    "source": "ue_mcp",
                    "dest": self.unreal_node_id,
                }
                self._send_message(self.mcast_sock, close_msg)

            if self.cmd_connection:
                self.cmd_connection.close()
                self.cmd_connection = None
            if self.cmd_sock:
                self.cmd_sock.close()
                self.cmd_sock = None
            if self.mcast_sock:
                self.mcast_sock.close()
                self.mcast_sock = None

            self.unreal_node_id = None
            logger.info("Connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {e}")

    def is_connected(self) -> bool:
        """Check if client is connected to UE5."""
        return self.cmd_connection is not None and self.unreal_node_id is not None

    def get_node_id(self) -> Optional[str]:
        """Get the connected node ID."""
        return self.unreal_node_id

    def verify_pid(self, expected_pid: int) -> bool:
        """
        Verify that the connected editor has the expected process ID.

        This executes a Python command in UE5 to get the OS process ID and
        compares it with the expected PID.

        Args:
            expected_pid: Expected process ID

        Returns:
            True if PID matches, False otherwise
        """
        if not self.is_connected():
            return False

        result = self.execute(
            "import os; print(os.getpid())",
            exec_type=self.ExecTypes.EXECUTE_STATEMENT,
            timeout=5.0,
        )

        if not result.get("success"):
            logger.warning("Failed to verify PID: execution failed")
            return False

        output = result.get("output", [])
        for line in output:
            if isinstance(line, dict):
                output_str = line.get("output", "")
            else:
                output_str = str(line)

            output_str = output_str.strip()
            if output_str.isdigit():
                actual_pid = int(output_str)
                if actual_pid == expected_pid:
                    logger.info(f"PID verification successful: {actual_pid}")
                    return True
                else:
                    logger.warning(
                        f"PID mismatch: expected {expected_pid}, got {actual_pid}"
                    )
                    return False

        logger.warning("Failed to verify PID: could not parse output")
        return False
