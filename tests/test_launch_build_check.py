
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from ue_mcp.editor_manager import EditorManager

PROJECT_PATH = Path("D:/Code/ue-mcp/tests/fixtures/EmptyCPPProject/EmptyCPPProject.uproject")

class TestLaunchBuildCheck:
    
    @pytest.fixture
    def manager(self):
        return EditorManager(PROJECT_PATH)

    @pytest.mark.asyncio
    async def test_launch_missing_binary(self, manager):
        """Test launch fails when C++ project binary is missing."""
        # 1. Force is_cpp_project to True
        with patch.object(EditorManager, 'is_cpp_project', return_value=True):
            # 2. Simulate missing binary
            # We patch Path.exists. Since it's called on a path computed inside, 
            # we need to be careful. The code does: dll_path.exists()
            # We can patch pathlib.Path.exists globally for the duration of this test
            with patch('pathlib.Path.exists', return_value=False):
                 result = await manager.launch()

        assert result['success'] is False
        assert "Project binary not found" in result['error']
        assert "project.build" in result['error']

    @pytest.mark.asyncio
    async def test_launch_outdated_binary(self, manager):
        """Test launch fails when Source files are newer than binary."""
        # Setup mocks
        mock_stat_binary = MagicMock()
        mock_stat_binary.st_mtime = 1000.0
        
        mock_stat_source = MagicMock()
        mock_stat_source.st_mtime = 2000.0 # Newer than binary

        # Configure stat side_effect
        def stat_side_effect(*args, **kwargs):
            # If the path ends with .dll (or is in Binaries), return mock_stat_binary
            # In the code: dll_path.stat().st_mtime
            # And: file_path.stat().st_mtime
            # We can detect based on the path string if possible, but args is empty for property access?
            # Wait, Path.stat() is a method.
            # But the mock receives 'self' as first arg if patched on class?
            # No, when patching 'pathlib.Path.stat', the first arg to side_effect is the Path instance.
            path_instance = args[0]
            if str(path_instance).endswith('.dll'):
                return mock_stat_binary
            else:
                return mock_stat_source

        # 3. Call launch (should fail)
        with patch.object(EditorManager, 'is_cpp_project', return_value=True), \
             patch('pathlib.Path.exists', return_value=True), \
             patch('ue_mcp.editor_manager.os.walk') as mock_walk, \
             patch('pathlib.Path.stat', side_effect=stat_side_effect):
             
             # Configure os.walk to return one source file
             mock_walk.return_value = [
                ("D:/Code/ue-mcp/tests/fixtures/EmptyCPPProject/Source", [], ["MyActor.cpp"])
             ]

             result = await manager.launch()

        assert result['success'] is False
        assert "Project needs to be built" in result['error']
        assert "Source file 'MyActor.cpp' is newer" in result['error']

    @pytest.mark.asyncio
    async def test_launch_needs_build_interception(self, manager):
        """
        Verify editor.launch calls needs_build and handles True result.
        This verifies the integration logic requested.
        """
        with patch.object(manager, 'needs_build', return_value=(True, "Testing missing binary")):
             result = await manager.launch()
        
        assert result['success'] is False
        assert "Project needs to be built" in result['error']
        assert "Testing missing binary" in result['error']
        assert "project.build" in result['error']

    def test_needs_build_logic_missing_binary(self, manager):
        """Test the actual needs_build logic for missing binary."""
        with patch.object(EditorManager, 'is_cpp_project', return_value=True), \
             patch('pathlib.Path.exists', return_value=False):
             
             needs_build, reason = manager.needs_build()
             
             assert needs_build is True
             assert "Project binary not found" in reason

