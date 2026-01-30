"""
ExGraphEditorLibrary API Tests using mcp-pytest fixtures.

Tests the Blueprint graph editing functionality in ExtraPythonAPIs plugin.
Uses ThirdPersonTemplate project for testing.

Tests:
1. Check if ExGraphEditorLibrary is available
2. Create Blueprint assets
3. Add function call and event nodes
4. Connect nodes and set pin values
5. Read node information
6. Delete nodes and disconnect pins
7. Compile blueprints

Usage:
    pytest tests/test_graph_editor_api.py -v -s

Requirements:
    - ThirdPersonTemplate project in tests/fixtures/
    - ExtraPythonAPIs plugin must be compiled and installed in the project
"""

import json
import asyncio
from pathlib import Path
from typing import Any

import pytest

from mcp_pytest import ToolCaller, ToolCallResult


# =============================================================================
# Helper Functions
# =============================================================================


def parse_tool_result(result: ToolCallResult) -> dict[str, Any]:
    """Parse tool result text content as JSON."""
    text = result.text_content
    if not text:
        return {"is_error": result.is_error, "content": str(result.result.content)}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


def extract_output_text(output: Any) -> str:
    """Extract text from output field which can be in different formats."""
    if output is None:
        return ""

    if isinstance(output, str):
        return output

    if isinstance(output, list):
        lines = []
        for item in output:
            if isinstance(item, str):
                lines.append(item)
            elif isinstance(item, dict):
                if "output" in item:
                    lines.append(str(item["output"]))
                else:
                    lines.append(str(item))
            else:
                lines.append(str(item))
        return "\n".join(lines)

    return str(output)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def thirdperson_template_path() -> Path:
    """Return the path to ThirdPersonTemplate fixture."""
    return Path(__file__).parent / "fixtures" / "ThirdPersonTemplate"


@pytest.fixture(scope="module")
def test_blueprint_path() -> str:
    """Return the asset path for test blueprints."""
    return "/Game/TestGraphEditor"


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
class TestGraphEditorAPIAvailability:
    """Test that ExGraphEditorLibrary is available."""

    @pytest.mark.asyncio
    async def test_check_library_available(self, running_editor: ToolCaller):
        """Test that ExGraphEditorLibrary is available in UE Python."""
        await asyncio.sleep(2)

        check_code = """
import unreal

# Check if ExGraphEditorLibrary class exists
try:
    lib = unreal.ExGraphEditorLibrary
    print("ExGraphEditorLibrary is available")

    # List available methods
    methods = [m for m in dir(lib) if not m.startswith('_')]
    print(f"Available methods: {methods}")

    result = {"available": True, "methods": methods}
except AttributeError as e:
    print(f"ExGraphEditorLibrary not found: {e}")
    result = {"available": False, "error": str(e)}

print(f"RESULT: {result}")
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": check_code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "ExGraphEditorLibrary is available" in output_text, (
            f"ExGraphEditorLibrary not available. Output: {output_text}"
        )


@pytest.mark.integration
@pytest.mark.slow
class TestGraphEditorCRUD:
    """Test CRUD operations for Blueprint graph editing."""

    @pytest.mark.asyncio
    async def test_create_blueprint_asset(self, running_editor: ToolCaller, test_blueprint_path: str):
        """Test creating a new Blueprint asset."""
        code = f"""
import unreal

# Create a new Blueprint
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "{test_blueprint_path}",
    "BP_TestActor",
    unreal.Actor.static_class()
)

if bp:
    print(f"Created Blueprint: {{bp.get_name()}}")
    result = {{"success": True, "name": bp.get_name()}}
else:
    print("Failed to create Blueprint")
    result = {{"success": False}}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Created Blueprint:" in output_text or '"success": true' in output_text.lower(), (
            f"Failed to create Blueprint. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_add_event_node(self, running_editor: ToolCaller, test_blueprint_path: str):
        """Test adding an event node (BeginPlay)."""
        code = f"""
import unreal

# Load the test Blueprint
bp = unreal.load_asset("{test_blueprint_path}/BP_TestActor")
if not bp:
    print("Blueprint not found, creating new one")
    bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
        "{test_blueprint_path}",
        "BP_TestActor",
        unreal.Actor.static_class()
    )

if bp:
    # Add BeginPlay event
    event_node = unreal.ExGraphEditorLibrary.add_event_node(
        bp,
        unreal.Actor.static_class(),
        "ReceiveBeginPlay",
        0, 0
    )

    if event_node:
        title = unreal.ExGraphEditorLibrary.get_node_title(event_node)
        pins = unreal.ExGraphEditorLibrary.get_node_pin_names(event_node)
        print(f"Added event node: {{title}}")
        print(f"Pins: {{[str(p) for p in pins]}}")
        result = {{"success": True, "title": title, "pin_count": len(pins)}}
    else:
        print("Failed to add event node")
        result = {{"success": False, "error": "add_event_node returned None"}}
else:
    result = {{"success": False, "error": "Blueprint not found"}}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Added event node:" in output_text or '"success": true' in output_text.lower(), (
            f"Failed to add event node. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_add_call_function_node(self, running_editor: ToolCaller, test_blueprint_path: str):
        """Test adding a function call node (GetTimeSeconds from GameplayStatics)."""
        code = f"""
import unreal

bp = unreal.load_asset("{test_blueprint_path}/BP_TestActor")
if bp:
    # Add GetTimeSeconds function call (GameplayStatics is exposed to Python)
    func_node = unreal.ExGraphEditorLibrary.add_call_function_node(
        bp,
        unreal.GameplayStatics.static_class(),
        "GetTimeSeconds",
        300, 0
    )

    if func_node:
        title = unreal.ExGraphEditorLibrary.get_node_title(func_node)
        pins = unreal.ExGraphEditorLibrary.get_node_pin_names(func_node)
        print(f"Added function node: {{title}}")
        print(f"Pins: {{[str(p) for p in pins]}}")
        result = {{"success": True, "title": title, "pin_count": len(pins)}}
    else:
        print("Failed to add function node")
        result = {{"success": False, "error": "add_call_function_node returned None"}}
else:
    result = {{"success": False, "error": "Blueprint not found"}}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Added function node:" in output_text or '"success": true' in output_text.lower(), (
            f"Failed to add function node. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_connect_nodes(self, running_editor: ToolCaller, test_blueprint_path: str):
        """Test connecting two nodes."""
        code = f"""
import unreal

bp = unreal.load_asset("{test_blueprint_path}/BP_TestActor")
if bp:
    # Add a function node to connect to
    func_node = unreal.ExGraphEditorLibrary.add_call_function_node(
        bp, unreal.Actor.static_class(), "K2_DestroyActor", 400, 0
    )

    # Get all nodes and find the BeginPlay event
    nodes = unreal.ExGraphEditorLibrary.get_all_nodes(bp)
    print(f"Found {{len(nodes)}} nodes")

    event_node = None
    for node in nodes:
        title = unreal.ExGraphEditorLibrary.get_node_title(node)
        if "BeginPlay" in title or "\u5f00\u59cb\u8fd0\u884c" in title:  # Chinese: 开始运行
            event_node = node
            break

    if event_node and func_node:
        # Connect event's exec pin to function's exec pin
        success = unreal.ExGraphEditorLibrary.connect_nodes(
            event_node, "then",
            func_node, "execute"
        )
        print(f"Connection result: {{success}}")
        result = {{"success": success}}
    else:
        print(f"Could not find both nodes. Event: {{event_node}}, Func: {{func_node}}")
        result = {{"success": False, "error": "Nodes not found"}}
else:
    result = {{"success": False, "error": "Blueprint not found"}}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Connection result: True" in output_text or '"success": true' in output_text.lower(), (
            f"Failed to connect nodes. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_set_pin_default_value(self, running_editor: ToolCaller, test_blueprint_path: str):
        """Test setting a pin's default value."""
        code = f"""
import unreal

bp = unreal.load_asset("{test_blueprint_path}/BP_TestActor")
if bp:
    # Add a SetGamePaused node which has a bool pin we can set
    func_node = unreal.ExGraphEditorLibrary.add_call_function_node(
        bp, unreal.GameplayStatics.static_class(), "SetGamePaused", 500, 0
    )

    if func_node:
        # Set the bPaused pin value to true
        success = unreal.ExGraphEditorLibrary.set_pin_default_value(
            func_node, "bPaused", "true"
        )
        print(f"Set pin value result: {{success}}")
        result = {{"success": success}}
    else:
        result = {{"success": False, "error": "Failed to add function node"}}
else:
    result = {{"success": False, "error": "Blueprint not found"}}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Set pin value result: True" in output_text or '"success": true' in output_text.lower(), (
            f"Failed to set pin value. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_compile_blueprint(self, running_editor: ToolCaller, test_blueprint_path: str):
        """Test compiling a Blueprint."""
        code = f"""
import unreal

bp = unreal.load_asset("{test_blueprint_path}/BP_TestActor")
if bp:
    success = unreal.ExGraphEditorLibrary.compile_blueprint(bp)
    print(f"Compile result: {{success}}")
    result = {{"success": success}}
else:
    result = {{"success": False, "error": "Blueprint not found"}}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Compile result: True" in output_text or '"success": true' in output_text.lower(), (
            f"Failed to compile Blueprint. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_get_all_nodes(self, running_editor: ToolCaller, test_blueprint_path: str):
        """Test getting all nodes from a Blueprint."""
        code = f"""
import unreal

bp = unreal.load_asset("{test_blueprint_path}/BP_TestActor")
if bp:
    nodes = unreal.ExGraphEditorLibrary.get_all_nodes(bp)
    print(f"Found {{len(nodes)}} nodes")

    for i, node in enumerate(nodes):
        title = unreal.ExGraphEditorLibrary.get_node_title(node)
        pins = unreal.ExGraphEditorLibrary.get_node_pin_names(node)
        print(f"Node {{i}}: {{title}} ({{len(pins)}} pins)")

    result = {{"success": True, "node_count": len(nodes)}}
else:
    result = {{"success": False, "error": "Blueprint not found"}}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Found" in output_text and "nodes" in output_text, (
            f"Failed to get nodes. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_disconnect_pin(self, running_editor: ToolCaller, test_blueprint_path: str):
        """Test disconnecting a pin."""
        code = f"""
import unreal

bp = unreal.load_asset("{test_blueprint_path}/BP_TestActor")
if bp:
    # Add and connect two nodes first
    event = unreal.ExGraphEditorLibrary.add_event_node(
        bp, unreal.Actor.static_class(), "ReceiveTick", 0, 200
    )
    func = unreal.ExGraphEditorLibrary.add_call_function_node(
        bp, unreal.Actor.static_class(), "K2_DestroyActor", 300, 200
    )

    if event and func:
        # Connect them first
        unreal.ExGraphEditorLibrary.connect_nodes(event, "then", func, "execute")

        # Now disconnect
        success = unreal.ExGraphEditorLibrary.disconnect_pin(func, "execute")
        print(f"Disconnect result: {{success}}")
        result = {{"success": success}}
    else:
        result = {{"success": False, "error": "Failed to create test nodes"}}
else:
    result = {{"success": False, "error": "Blueprint not found"}}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Disconnect result: True" in output_text or '"success": true' in output_text.lower(), (
            f"Failed to disconnect pin. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_delete_node(self, running_editor: ToolCaller, test_blueprint_path: str):
        """Test deleting a node."""
        code = f"""
import unreal

bp = unreal.load_asset("{test_blueprint_path}/BP_TestActor")
if bp:
    # Add a node specifically to delete
    func_node = unreal.ExGraphEditorLibrary.add_call_function_node(
        bp, unreal.GameplayStatics.static_class(), "GetTimeSeconds", 600, 200
    )

    nodes_before = unreal.ExGraphEditorLibrary.get_all_nodes(bp)
    initial_count = len(nodes_before)
    print(f"Initial node count: {{initial_count}}")

    if func_node:
        success = unreal.ExGraphEditorLibrary.delete_node(bp, func_node)
        print(f"Delete result: {{success}}")

        # Verify node was deleted
        nodes_after = unreal.ExGraphEditorLibrary.get_all_nodes(bp)
        print(f"Node count after delete: {{len(nodes_after)}}")

        result = {{
            "success": success,
            "initial_count": initial_count,
            "final_count": len(nodes_after)
        }}
    else:
        result = {{"success": False, "error": "Failed to add test node"}}
else:
    result = {{"success": False, "error": "Blueprint not found"}}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Delete result: True" in output_text or '"success": true' in output_text.lower(), (
            f"Failed to delete node. Output: {output_text}"
        )


@pytest.mark.integration
@pytest.mark.slow
class TestGraphEditorIntegration:
    """Integration tests for complete Blueprint creation workflow."""

    @pytest.mark.asyncio
    async def test_create_simple_blueprint_logic(self, running_editor: ToolCaller):
        """
        Integration test: Create a Blueprint with BeginPlay -> K2_DestroyActor logic.
        """
        code = """
import unreal

# Create a fresh test Blueprint
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/TestGraphEditor",
    "BP_IntegrationTest",
    unreal.Actor.static_class()
)

if not bp:
    print("Failed to create Blueprint")
    result = {"success": False, "error": "Blueprint creation failed"}
else:
    print(f"Created Blueprint: {bp.get_name()}")

    # Step 1: Add BeginPlay event
    event_node = unreal.ExGraphEditorLibrary.add_event_node(
        bp,
        unreal.Actor.static_class(),
        "ReceiveBeginPlay",
        0, 0
    )
    print(f"Added event node: {event_node is not None}")

    # Step 2: Add K2_DestroyActor function (has exec pins, good for testing connection)
    func_node = unreal.ExGraphEditorLibrary.add_call_function_node(
        bp,
        unreal.Actor.static_class(),
        "K2_DestroyActor",
        300, 0
    )
    print(f"Added function node: {func_node is not None}")

    # Step 3: Connect BeginPlay -> K2_DestroyActor
    connected = unreal.ExGraphEditorLibrary.connect_nodes(
        event_node, "then",
        func_node, "execute"
    )
    print(f"Connected nodes: {connected}")

    # Step 4: Compile
    compiled = unreal.ExGraphEditorLibrary.compile_blueprint(bp)
    print(f"Compiled: {compiled}")

    result = {
        "success": all([event_node, func_node, connected, compiled]),
        "steps": {
            "event_node": event_node is not None,
            "func_node": func_node is not None,
            "connected": connected,
            "compiled": compiled
        }
    }

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=120,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        # Verify compilation succeeded
        assert "Compiled: True" in output_text, (
            f"Integration test failed - compilation failed. Output: {output_text}"
        )


@pytest.mark.integration
@pytest.mark.slow
class TestPhase4APIs:
    """Test Phase 4 APIs: Branch nodes, Variables, and member variable creation."""

    @pytest.mark.asyncio
    async def test_add_branch_node(self, running_editor: ToolCaller):
        """Test adding a Branch (if-then-else) node."""
        code = """
import unreal

# Create a test Blueprint
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/TestGraphEditor",
    "BP_BranchTest",
    unreal.Actor.static_class()
)

if bp:
    # Add Branch node
    branch_node = unreal.ExGraphEditorLibrary.add_branch_node(bp, 200, 100)

    if branch_node:
        title = unreal.ExGraphEditorLibrary.get_node_title(branch_node)
        pins = unreal.ExGraphEditorLibrary.get_node_pin_names(branch_node)
        print(f"Added branch node: {title}")
        print(f"Pins: {[str(p) for p in pins]}")

        # Compile to verify
        compiled = unreal.ExGraphEditorLibrary.compile_blueprint(bp)
        print(f"Compiled: {compiled}")

        result = {"success": True, "title": title, "pin_count": len(pins), "compiled": compiled}
    else:
        result = {"success": False, "error": "Failed to add branch node"}
else:
    result = {"success": False, "error": "Blueprint not created"}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Added branch node:" in output_text, (
            f"Failed to add branch node. Output: {output_text}"
        )
        assert "Compiled: True" in output_text, (
            f"Branch node blueprint failed to compile. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_add_member_variable(self, running_editor: ToolCaller):
        """Test adding member variables to a Blueprint."""
        code = """
import unreal

# Create a test Blueprint
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/TestGraphEditor",
    "BP_VariableTest",
    unreal.Actor.static_class()
)

if bp:
    # Check initial variables
    vars_before = unreal.ExGraphEditorLibrary.get_blueprint_variables(bp)
    print(f"Variables before: {[str(v) for v in vars_before]}")

    # Add variables of different types
    add_results = []
    test_vars = [
        ("TestInt", "int"),
        ("TestFloat", "float"),
        ("TestBool", "bool"),
        ("TestString", "string"),
        ("TestVector", "vector"),
    ]

    for var_name, var_type in test_vars:
        success = unreal.ExGraphEditorLibrary.add_member_variable(
            bp, unreal.Name(var_name), var_type
        )
        add_results.append((var_name, success))
        print(f"Add {var_name} ({var_type}): {success}")

    # Check variables after
    vars_after = unreal.ExGraphEditorLibrary.get_blueprint_variables(bp)
    print(f"Variables after: {[str(v) for v in vars_after]}")

    # Compile to verify
    compiled = unreal.ExGraphEditorLibrary.compile_blueprint(bp)
    print(f"Compiled: {compiled}")

    result = {
        "success": len(vars_after) == len(test_vars),
        "var_count": len(vars_after),
        "compiled": compiled
    }
else:
    result = {"success": False, "error": "Blueprint not created"}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Add TestInt (int): True" in output_text, (
            f"Failed to add int variable. Output: {output_text}"
        )
        assert "Add TestVector (vector): True" in output_text, (
            f"Failed to add vector variable. Output: {output_text}"
        )
        assert "Compiled: True" in output_text, (
            f"Variable test blueprint failed to compile. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_variable_get_set_nodes(self, running_editor: ToolCaller):
        """Test adding VariableGet and VariableSet nodes."""
        code = """
import unreal

# Load the variable test Blueprint we created in previous test
bp = unreal.load_asset("/Game/TestGraphEditor/BP_VariableTest")
if not bp:
    # Create it if not found
    bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
        "/Game/TestGraphEditor",
        "BP_VariableTest2",
        unreal.Actor.static_class()
    )
    # Add a variable
    unreal.ExGraphEditorLibrary.add_member_variable(bp, unreal.Name("TestVar"), "int")
    unreal.ExGraphEditorLibrary.compile_blueprint(bp)

if bp:
    # Get variables
    variables = unreal.ExGraphEditorLibrary.get_blueprint_variables(bp)
    print(f"Variables: {[str(v) for v in variables]}")

    if len(variables) > 0:
        test_var = variables[0]

        # Add VariableGet node
        get_node = unreal.ExGraphEditorLibrary.add_variable_get_node(
            bp, test_var, 400, 0
        )

        if get_node:
            get_title = unreal.ExGraphEditorLibrary.get_node_title(get_node)
            get_pins = unreal.ExGraphEditorLibrary.get_node_pin_names(get_node)
            print(f"VariableGet: {get_title}, pins: {[str(p) for p in get_pins]}")
        else:
            print("VariableGet: Failed")

        # Add VariableSet node
        set_node = unreal.ExGraphEditorLibrary.add_variable_set_node(
            bp, test_var, 400, 150
        )

        if set_node:
            set_title = unreal.ExGraphEditorLibrary.get_node_title(set_node)
            set_pins = unreal.ExGraphEditorLibrary.get_node_pin_names(set_node)
            print(f"VariableSet: {set_title}, pins: {[str(p) for p in set_pins]}")
        else:
            print("VariableSet: Failed")

        # Compile to verify
        compiled = unreal.ExGraphEditorLibrary.compile_blueprint(bp)
        print(f"Compiled: {compiled}")

        result = {
            "success": get_node is not None and set_node is not None and compiled,
            "get_node": get_node is not None,
            "set_node": set_node is not None,
            "compiled": compiled
        }
    else:
        result = {"success": False, "error": "No variables in Blueprint"}
else:
    result = {"success": False, "error": "Blueprint not found"}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "VariableGet:" in output_text and "pins:" in output_text, (
            f"Failed to add VariableGet node. Output: {output_text}"
        )
        assert "VariableSet:" in output_text and "pins:" in output_text, (
            f"Failed to add VariableSet node. Output: {output_text}"
        )
        assert "Compiled: True" in output_text, (
            f"Variable node test blueprint failed to compile. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_branch_with_variable_condition(self, running_editor: ToolCaller):
        """
        Integration test: Create logic with Branch node using variable as condition.
        BeginPlay -> Get variable -> Branch -> (true/false paths)
        """
        code = """
import unreal

# Create a test Blueprint
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/TestGraphEditor",
    "BP_BranchWithVariable",
    unreal.Actor.static_class()
)

if bp:
    # Add a bool variable
    var_added = unreal.ExGraphEditorLibrary.add_member_variable(
        bp, unreal.Name("bShouldDestroy"), "bool"
    )
    print(f"Variable added: {var_added}")

    # Compile to create the property
    unreal.ExGraphEditorLibrary.compile_blueprint(bp)

    # Get BeginPlay event node (auto-created)
    nodes = unreal.ExGraphEditorLibrary.get_all_nodes(bp)
    begin_play = None
    for node in nodes:
        title = unreal.ExGraphEditorLibrary.get_node_title(node)
        if "BeginPlay" in title or "开始运行" in title:
            begin_play = node
            break

    # Add nodes
    get_var = unreal.ExGraphEditorLibrary.add_variable_get_node(
        bp, unreal.Name("bShouldDestroy"), 200, 0
    )
    branch = unreal.ExGraphEditorLibrary.add_branch_node(bp, 400, 0)

    print(f"BeginPlay: {begin_play is not None}")
    print(f"Get variable: {get_var is not None}")
    print(f"Branch: {branch is not None}")

    # Connect: BeginPlay -> Branch exec
    if begin_play and branch:
        exec_connected = unreal.ExGraphEditorLibrary.connect_nodes(
            begin_play, "then",
            branch, "execute"
        )
        print(f"Exec connected: {exec_connected}")

    # Connect: Variable -> Branch condition
    if get_var and branch:
        cond_connected = unreal.ExGraphEditorLibrary.connect_nodes(
            get_var, "bShouldDestroy",  # Output pin name is the variable name
            branch, "Condition"
        )
        print(f"Condition connected: {cond_connected}")

    # Final compile
    compiled = unreal.ExGraphEditorLibrary.compile_blueprint(bp)
    print(f"Final compile: {compiled}")

    result = {
        "success": compiled,
        "var_added": var_added,
        "nodes_created": all([begin_play, get_var, branch]),
        "compiled": compiled
    }
else:
    result = {"success": False, "error": "Blueprint not created"}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=120,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Variable added: True" in output_text, (
            f"Failed to add variable. Output: {output_text}"
        )
        assert "Branch: True" in output_text, (
            f"Failed to create branch node. Output: {output_text}"
        )
        assert "Final compile: True" in output_text, (
            f"Integration test failed - compilation failed. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_add_member_function_node(self, running_editor: ToolCaller):
        """
        Test adding member function nodes for various classes using OwnerClass parameter.
        This tests the enhanced AddFunctionNodeByName API that supports ANY class's member methods.

        Note: In UE5, Blueprint-callable member methods use K2_ prefix (e.g., K2_GetActorLocation).
        """
        code = """
import unreal

# Create a test Blueprint
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/TestGraphEditor",
    "BP_MemberFuncTest",
    unreal.Actor.static_class()
)

if bp:
    results = {}

    # Test 1: Actor.K2_GetActorLocation (member method - note K2_ prefix)
    get_loc = unreal.ExGraphEditorLibrary.add_function_node_by_name(
        bp, "K2_GetActorLocation", unreal.Actor.static_class(), 0, 0
    )
    results["K2_GetActorLocation"] = get_loc is not None
    print(f"Actor.K2_GetActorLocation: {get_loc is not None}")

    # Test 2: Actor.K2_SetActorLocation (member method with params)
    set_loc = unreal.ExGraphEditorLibrary.add_function_node_by_name(
        bp, "K2_SetActorLocation", unreal.Actor.static_class(), 200, 0
    )
    results["K2_SetActorLocation"] = set_loc is not None
    print(f"Actor.K2_SetActorLocation: {set_loc is not None}")

    # Test 3: Verify Target/self pin exists for member method
    if get_loc:
        pins = unreal.ExGraphEditorLibrary.get_node_pin_names(get_loc)
        pin_strs = [str(p).lower() for p in pins]
        print(f"K2_GetActorLocation pins: {[str(p) for p in pins]}")
        # Member methods should have a self/target pin
        has_self = any("self" in p or "target" in p for p in pin_strs)
        results["has_self_pin"] = has_self
        print(f"Has self/target pin: {has_self}")

    # Test 4: SceneComponent.K2_GetComponentLocation
    get_comp_loc = unreal.ExGraphEditorLibrary.add_function_node_by_name(
        bp, "K2_GetComponentLocation", unreal.SceneComponent.static_class(), 400, 0
    )
    results["K2_GetComponentLocation"] = get_comp_loc is not None
    print(f"SceneComponent.K2_GetComponentLocation: {get_comp_loc is not None}")

    # Compile to verify all nodes are valid
    compiled = unreal.ExGraphEditorLibrary.compile_blueprint(bp)
    results["compiled"] = compiled
    print(f"Compiled: {compiled}")

    result = {"success": all(results.values()), "results": results}
else:
    result = {"success": False, "error": "Blueprint not created"}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "Actor.K2_GetActorLocation: True" in output_text, (
            f"Failed to add Actor.K2_GetActorLocation node. Output: {output_text}"
        )
        assert "Actor.K2_SetActorLocation: True" in output_text, (
            f"Failed to add Actor.K2_SetActorLocation node. Output: {output_text}"
        )
        assert "Has self/target pin: True" in output_text, (
            f"Member method should have self/target pin. Output: {output_text}"
        )
        assert "Compiled: True" in output_text, (
            f"Member function test blueprint failed to compile. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_add_function_node_backward_compatibility(self, running_editor: ToolCaller):
        """
        Test that AddFunctionNodeByName still works without OwnerClass (backward compatibility).
        Library functions like PrintString should work without specifying OwnerClass.
        """
        code = """
import unreal

# Create a test Blueprint
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/TestGraphEditor",
    "BP_BackwardCompatTest",
    unreal.Actor.static_class()
)

if bp:
    # Test: PrintString without OwnerClass (should still work)
    print_node = unreal.ExGraphEditorLibrary.add_function_node_by_name(
        bp, "PrintString", None, 0, 0
    )
    print(f"PrintString (no OwnerClass): {print_node is not None}")

    # Test: Delay without OwnerClass
    delay_node = unreal.ExGraphEditorLibrary.add_function_node_by_name(
        bp, "Delay", None, 200, 0
    )
    print(f"Delay (no OwnerClass): {delay_node is not None}")

    compiled = unreal.ExGraphEditorLibrary.compile_blueprint(bp)
    print(f"Compiled: {compiled}")

    result = {
        "success": print_node is not None and compiled,
        "print_node": print_node is not None,
        "delay_node": delay_node is not None,
        "compiled": compiled
    }
else:
    result = {"success": False, "error": "Blueprint not created"}

import json
print(json.dumps(result))
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = extract_output_text(output)

        assert "PrintString (no OwnerClass): True" in output_text, (
            f"Backward compatibility broken - PrintString without OwnerClass failed. Output: {output_text}"
        )
        assert "Compiled: True" in output_text, (
            f"Backward compatibility test blueprint failed to compile. Output: {output_text}"
        )
