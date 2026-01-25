"""UE5 Python API search tool."""

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..state import ServerState


def register_tools(mcp: "FastMCP", state: "ServerState") -> None:
    """Register API search tools."""

    from ..script_executor import execute_script_from_path, get_extra_scripts_dir

    from ._helpers import parse_json_result

    @mcp.tool(name="python_api_search")
    def python_api_search(
        mode: Annotated[
            str,
            Field(
                description="Query mode: 'list_classes', 'list_functions', 'class_info', 'member_info', 'search'"
            ),
        ],
        query: Annotated[
            str | None,
            Field(
                default=None,
                description="Class name, member path (Class.member), search term, or wildcard pattern (e.g., '*Actor*')",
            ),
        ],
        include_inherited: Annotated[
            bool,
            Field(
                default=True,
                description="For class_info: include inherited members",
            ),
        ],
        include_private: Annotated[
            bool,
            Field(
                default=False,
                description="Include private members (_underscore)",
            ),
        ],
        limit: Annotated[
            int,
            Field(default=100, description="Maximum results to return"),
        ],
    ) -> dict[str, Any]:
        """
        Query UE5 Python APIs from the running editor using runtime introspection.

        This tool introspects the live 'unreal' module in the running editor,
        providing accurate API information for the current UE5 version.

        Args:
            mode: Query mode - one of:
                - "list_classes": List all classes (supports wildcard pattern in query)
                - "list_functions": List functions/methods (supports multiple formats, see below)
                - "class_info": Get class details with all members (requires query)
                - "member_info": Get specific member details (requires query)
                - "search": Fuzzy search across all names (requires query)
            query: Depends on mode:
                - list_classes: Optional wildcard pattern (e.g., "*Actor*", "Static*")
                - list_functions: Multiple formats supported:
                    - None or no ".": Module-level functions (e.g., "*asset*")
                    - "ClassName.*": All methods of a class (e.g., "Actor.*")
                    - "ClassName.*pattern*": Methods matching pattern (e.g., "Actor.*location*")
                    - "*.*pattern*": Search methods across all classes (e.g., "*.*spawn*")
                - class_info: Class name (e.g., "Actor")
                - member_info: Member path (e.g., "Actor.get_actor_location")
                - search: Search term (e.g., "spawn")
            include_inherited: For class_info: include inherited members (default: True)
            include_private: Include private members starting with underscore (default: False)
            limit: Maximum number of results to return (default: 100)

        Returns:
            Result containing:
            - success: Whether query succeeded
            - mode: The query mode used
            - results: (for list/search modes) List of matching items
            - pattern: (for list modes with query) The wildcard pattern used
            - class_name/member_name: (for info modes) The queried item
            - properties/methods: (for class_info) Lists of class members
            - signature/docstring: (for member_info) Member details
            - error: Error message (if failed)

        Examples:
            # List all classes
            python_api_search(mode="list_classes", limit=10)

            # List classes matching wildcard pattern
            python_api_search(mode="list_classes", query="*Actor*")
            python_api_search(mode="list_classes", query="Static*")

            # List module-level functions
            python_api_search(mode="list_functions")
            python_api_search(mode="list_functions", query="*asset*")

            # List all methods of a class
            python_api_search(mode="list_functions", query="Actor.*")

            # List methods matching pattern in a class
            python_api_search(mode="list_functions", query="Actor.*location*")

            # Search methods across all classes
            python_api_search(mode="list_functions", query="*.*spawn*")

            # Get Actor class info
            python_api_search(mode="class_info", query="Actor")

            # Get specific method info
            python_api_search(mode="member_info", query="Actor.get_actor_location")

            # Search for spawn-related APIs
            python_api_search(mode="search", query="spawn")
        """
        execution = state.get_execution_subsystem()

        # Validate mode
        valid_modes = [
            "list_classes",
            "list_functions",
            "class_info",
            "member_info",
            "search",
        ]
        if mode not in valid_modes:
            return {
                "success": False,
                "error": f"Invalid mode '{mode}'. Must be one of: {valid_modes}",
            }

        # Validate query required for certain modes
        if mode in ["class_info", "member_info", "search"] and not query:
            return {
                "success": False,
                "error": f"query parameter required for mode '{mode}'",
            }

        # Execute api_search script
        script_path = get_extra_scripts_dir() / "api_search.py"
        params = {
            "mode": mode,
            "query": query,
            "include_inherited": include_inherited,
            "include_private": include_private,
            "limit": limit,
        }

        result = execute_script_from_path(execution, script_path, params, timeout=30.0)

        # Parse result
        return parse_json_result(result)
