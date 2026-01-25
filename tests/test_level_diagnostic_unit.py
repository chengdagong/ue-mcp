"""
Unit tests for LevelDiagnostic class.

Tests the diagnostic logic without requiring UE5 editor by mocking the unreal module.

Usage:
    pytest tests/test_level_diagnostic_unit.py -v
"""

import sys
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

# Add asset_diagnostic to path
SITE_PACKAGES_PATH = Path(__file__).parent.parent / "src" / "ue_mcp" / "extra" / "site-packages"
if str(SITE_PACKAGES_PATH) not in sys.path:
    sys.path.insert(0, str(SITE_PACKAGES_PATH))


# Create mock unreal module before importing the diagnostic module
@pytest.fixture
def mock_unreal():
    """Mock the unreal module for all tests in this file."""
    mock_module = MagicMock()

    # Mock Vector class
    class MockVector:
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x = x
            self.y = y
            self.z = z

    mock_module.Vector = MockVector

    # Mock Actor class
    class MockActor:
        def __init__(self, class_name: str, label: str = ""):
            self._class_name = class_name
            self._label = label or class_name
            self._location = MockVector(0, 0, 0)
            self._rotation = MagicMock(pitch=0, roll=0, yaw=0)
            self._tags = []

        def get_class(self):
            mock_class = MagicMock()
            mock_class.get_name.return_value = self._class_name
            return mock_class

        def get_actor_label(self):
            return self._label

        def get_actor_location(self):
            return self._location

        def get_actor_rotation(self):
            return self._rotation

        @property
        def tags(self):
            return self._tags

    mock_module.Actor = MockActor

    # Mock other UE classes
    mock_module.PlayerStart = type("PlayerStart", (MockActor,), {})
    mock_module.Character = type("Character", (MockActor,), {})
    mock_module.Pawn = type("Pawn", (MockActor,), {})
    mock_module.StaticMeshActor = type("StaticMeshActor", (MockActor,), {})

    # Store MockActor for test use
    mock_module._MockActor = MockActor

    # Patch the module
    with patch.dict(sys.modules, {"unreal": mock_module}):
        yield mock_module


class TestLightingDiagnostic:
    """Unit tests for the _check_lighting_actors method."""

    def _create_mock_actors(self, mock_unreal, class_names: List[str]) -> List:
        """Create a list of mock actors with given class names."""
        MockActor = mock_unreal._MockActor
        return [MockActor(name, label=f"{name}_Instance") for name in class_names]

    def _create_diagnostic_and_result(self, mock_unreal):
        """Create a LevelDiagnostic instance and DiagnosticResult."""
        # Import after mocking
        from asset_diagnostic.core import AssetType, DiagnosticResult, IssueSeverity
        from asset_diagnostic.diagnostics.level import LevelDiagnostic

        diagnostic = LevelDiagnostic()
        result = DiagnosticResult(
            asset_path="/Game/TestLevel",
            asset_type=AssetType.LEVEL,
            asset_name="TestLevel",
        )
        return diagnostic, result, IssueSeverity

    def test_all_lighting_actors_present(self, mock_unreal):
        """Test that no warning is generated when all essential lighting actors are present."""
        # Create actors with all essential lighting classes
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "DirectionalLight",
                "SkyLight",
                "SkyAtmosphere",
                "ExponentialHeightFog",
                "StaticMeshActor",  # Non-lighting actor
            ],
        )

        diagnostic, result, _ = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        # Should have no issues
        assert len(result.issues) == 0
        assert result.metadata["lighting_actors_found"] == 4
        assert result.metadata["lighting_actors_missing"] == 0

    def test_missing_directional_light(self, mock_unreal):
        """Test warning when DirectionalLight is missing."""
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "SkyLight",
                "SkyAtmosphere",
                "ExponentialHeightFog",
            ],
        )

        diagnostic, result, IssueSeverity = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        # Should have 1 warning
        assert len(result.issues) == 1
        assert result.issues[0].severity == IssueSeverity.WARNING
        assert result.issues[0].category == "Lighting"
        assert "DirectionalLight" in result.issues[0].message or "1 of 4" in result.issues[0].message
        assert result.metadata["lighting_actors_missing"] == 1

    def test_missing_sky_light(self, mock_unreal):
        """Test warning when SkyLight is missing."""
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "DirectionalLight",
                "SkyAtmosphere",
                "ExponentialHeightFog",
            ],
        )

        diagnostic, result, IssueSeverity = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        assert len(result.issues) == 1
        assert result.issues[0].severity == IssueSeverity.WARNING
        assert result.metadata["lighting_actors_missing"] == 1

    def test_missing_sky_atmosphere(self, mock_unreal):
        """Test warning when SkyAtmosphere is missing."""
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "DirectionalLight",
                "SkyLight",
                "ExponentialHeightFog",
            ],
        )

        diagnostic, result, IssueSeverity = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        assert len(result.issues) == 1
        assert result.issues[0].severity == IssueSeverity.WARNING
        assert result.metadata["lighting_actors_missing"] == 1

    def test_missing_exponential_height_fog(self, mock_unreal):
        """Test warning when ExponentialHeightFog is missing."""
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "DirectionalLight",
                "SkyLight",
                "SkyAtmosphere",
            ],
        )

        diagnostic, result, IssueSeverity = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        assert len(result.issues) == 1
        assert result.issues[0].severity == IssueSeverity.WARNING
        assert result.metadata["lighting_actors_missing"] == 1

    def test_missing_multiple_lighting_actors(self, mock_unreal):
        """Test warning when multiple lighting actors are missing."""
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "DirectionalLight",
                # Missing: SkyLight, SkyAtmosphere, ExponentialHeightFog
            ],
        )

        diagnostic, result, IssueSeverity = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        assert len(result.issues) == 1
        assert result.issues[0].severity == IssueSeverity.WARNING
        assert "3 of 4" in result.issues[0].message
        assert result.metadata["lighting_actors_missing"] == 3
        assert result.metadata["lighting_actors_found"] == 1

    def test_no_lighting_actors(self, mock_unreal):
        """Test warning when all lighting actors are missing."""
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "StaticMeshActor",
                "PlayerStart",
            ],
        )

        diagnostic, result, IssueSeverity = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        assert len(result.issues) == 1
        assert result.issues[0].severity == IssueSeverity.WARNING
        assert "4 of 4" in result.issues[0].message
        assert result.metadata["lighting_actors_missing"] == 4
        assert result.metadata["lighting_actors_found"] == 0

    def test_subclass_detection(self, mock_unreal):
        """Test that subclasses of lighting actors are detected (e.g., BP_DirectionalLight_C)."""
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "BP_DirectionalLight_C",  # Blueprint subclass
                "SkyLight",
                "SkyAtmosphere",
                "ExponentialHeightFog",
            ],
        )

        diagnostic, result, _ = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        # BP_DirectionalLight_C should be detected as DirectionalLight
        assert len(result.issues) == 0
        assert result.metadata["lighting_actors_found"] == 4

    def test_empty_actor_list(self, mock_unreal):
        """Test with empty actor list."""
        actors = []

        diagnostic, result, IssueSeverity = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        # Should warn about all missing
        assert len(result.issues) == 1
        assert result.issues[0].severity == IssueSeverity.WARNING
        assert result.metadata["lighting_actors_missing"] == 4

    def test_issue_details_format(self, mock_unreal):
        """Test that issue details follow the expected format."""
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "DirectionalLight",
                # Missing others
            ],
        )

        diagnostic, result, _ = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        assert len(result.issues) == 1
        issue = result.issues[0]

        # Check details contain expected sections
        details_text = "\n".join(issue.details)
        assert "[CONTEXT]" in details_text
        assert "[DATA]" in details_text
        assert "[EXPECTED]" in details_text
        assert "[IMPACT]" in details_text
        assert "[INFO]" in details_text

        # Check suggestion is present
        assert issue.suggestion is not None
        assert "Add missing lighting actors" in issue.suggestion

    def test_metadata_stored(self, mock_unreal):
        """Test that lighting metadata is properly stored in result."""
        actors = self._create_mock_actors(
            mock_unreal,
            [
                "DirectionalLight",
                "SkyLight",
            ],
        )

        diagnostic, result, _ = self._create_diagnostic_and_result(mock_unreal)
        diagnostic._check_lighting_actors(actors, result)

        # Check metadata keys exist
        assert "lighting_actors_found" in result.metadata
        assert "lighting_actors_missing" in result.metadata
        assert result.metadata["lighting_actors_found"] == 2
        assert result.metadata["lighting_actors_missing"] == 2
