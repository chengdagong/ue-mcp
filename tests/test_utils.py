"""Tests for ue_mcp.utils module."""

from pathlib import Path

import pytest

from ue_mcp.utils import (
    find_ue5_project_root,
    find_uproject_file,
    get_project_name,
)


class TestFindUprojectFile:
    """Tests for find_uproject_file function."""

    def test_find_in_current_dir(self, temp_project: Path):
        """Test finding .uproject in the current directory."""
        result = find_uproject_file(temp_project)
        assert result is not None
        assert result.name == "EmptyProjectTemplate.uproject"
        assert result.exists()

    def test_find_in_parent_dir(self, temp_project: Path):
        """Test finding .uproject by searching upward from subdirectory."""
        subdir = temp_project / "Content"
        subdir.mkdir(exist_ok=True)

        result = find_uproject_file(subdir)
        assert result is not None
        assert result.name == "EmptyProjectTemplate.uproject"

    def test_find_from_deep_subdir(self, temp_project: Path):
        """Test finding .uproject from deeply nested subdirectory."""
        deep_dir = temp_project / "Content" / "Blueprints" / "Characters"
        deep_dir.mkdir(parents=True, exist_ok=True)

        result = find_uproject_file(deep_dir)
        assert result is not None
        assert result.name == "EmptyProjectTemplate.uproject"

    def test_not_found(self, tmp_path: Path):
        """Test returning None when no .uproject file exists."""
        result = find_uproject_file(tmp_path)
        assert result is None

    def test_empty_directory(self, tmp_path: Path):
        """Test returning None for empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = find_uproject_file(empty_dir)
        assert result is None


class TestFindUe5ProjectRoot:
    """Tests for find_ue5_project_root function."""

    def test_find_root_from_project_dir(self, temp_project: Path):
        """Test finding project root from the project directory itself."""
        result = find_ue5_project_root(temp_project)
        assert result is not None
        assert result == temp_project

    def test_find_root_from_subdirectory(self, temp_project: Path):
        """Test finding project root from a subdirectory."""
        config_dir = temp_project / "Config"

        result = find_ue5_project_root(config_dir)
        assert result is not None
        assert result == temp_project

    def test_returns_none_for_non_project_dir(self, tmp_path: Path):
        """Test returning None for directory without .uproject."""
        result = find_ue5_project_root(tmp_path)
        assert result is None


class TestGetProjectName:
    """Tests for get_project_name function."""

    def test_extract_name(self, temp_uproject: Path):
        """Test extracting project name from .uproject path."""
        name = get_project_name(temp_uproject)
        assert name == "EmptyProjectTemplate"

    def test_extract_name_simple(self):
        """Test extracting project name from simple path."""
        path = Path("/some/path/MyGame.uproject")
        name = get_project_name(path)
        assert name == "MyGame"

    def test_extract_name_with_spaces(self):
        """Test extracting project name with spaces."""
        path = Path("/some/path/My Cool Game.uproject")
        name = get_project_name(path)
        assert name == "My Cool Game"

    def test_extract_name_with_underscores(self):
        """Test extracting project name with underscores."""
        path = Path("/some/path/My_Game_Project.uproject")
        name = get_project_name(path)
        assert name == "My_Game_Project"
