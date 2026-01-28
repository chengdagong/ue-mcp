"""Unit tests for image processing utilities."""

import base64
import io
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from ue_mcp.core.image_processing import (
    CLAUDE_AI_CLIENT_NAME,
    find_images_in_directory,
    image_to_base64,
    is_claude_ai_client,
    is_image_file,
    process_result_for_images,
)


def create_test_image(path: Path, width: int = 100, height: int = 100, color: tuple = (255, 0, 0)) -> None:
    """Create a valid test image file using Pillow.

    Args:
        path: Path to save the image
        width: Image width in pixels
        height: Image height in pixels
        color: RGB color tuple for the image
    """
    img = Image.new("RGB", (width, height), color)
    # Determine format from extension
    ext = path.suffix.lower()
    fmt = {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".bmp": "BMP",
        ".gif": "GIF",
        ".tiff": "TIFF",
    }.get(ext, "PNG")
    img.save(path, format=fmt)


class TestIsClaudeAiClient:
    """Tests for is_claude_ai_client function."""

    def test_exact_match_returns_true(self):
        """Test that exact match 'claude-ai' returns True."""
        assert is_claude_ai_client("claude-ai") is True

    def test_different_name_returns_false(self):
        """Test that different client names return False."""
        assert is_claude_ai_client("vscode") is False
        assert is_claude_ai_client("Automatic-Testing") is False
        assert is_claude_ai_client("unknown") is False

    def test_case_sensitive(self):
        """Test that matching is case-sensitive."""
        assert is_claude_ai_client("Claude-AI") is False
        assert is_claude_ai_client("CLAUDE-AI") is False
        assert is_claude_ai_client("Claude-ai") is False

    def test_none_returns_false(self):
        """Test that None returns False."""
        assert is_claude_ai_client(None) is False

    def test_empty_string_returns_false(self):
        """Test that empty string returns False."""
        assert is_claude_ai_client("") is False

    def test_constant_value(self):
        """Test that the constant has the expected value."""
        assert CLAUDE_AI_CLIENT_NAME == "claude-ai"


class TestIsImageFile:
    """Tests for is_image_file function."""

    @pytest.mark.parametrize(
        "filename",
        [
            "test.png",
            "test.PNG",
            "test.jpg",
            "test.JPG",
            "test.jpeg",
            "test.JPEG",
            "test.bmp",
            "test.gif",
            "test.tiff",
        ],
    )
    def test_image_extensions_return_true(self, filename: str):
        """Test that image extensions are recognized."""
        assert is_image_file(Path(filename)) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "test.txt",
            "test.py",
            "test.json",
            "test.mp4",
            "test.pdf",
            "test",
        ],
    )
    def test_non_image_extensions_return_false(self, filename: str):
        """Test that non-image extensions are not recognized."""
        assert is_image_file(Path(filename)) is False


class TestImageToBase64:
    """Tests for image_to_base64 function."""

    def test_converts_existing_image(self, tmp_path: Path):
        """Test that existing image is converted to base64 JPEG."""
        img_path = tmp_path / "test.png"
        create_test_image(img_path, width=100, height=100, color=(255, 0, 0))

        result = image_to_base64(img_path)

        assert result is not None
        assert result["path"] == str(img_path)
        # Now converts to JPEG
        assert result["mime_type"] == "image/jpeg"
        assert result["size_bytes"] > 0
        # Verify base64 can be decoded back to valid JPEG
        decoded = base64.standard_b64decode(result["data"])
        # Verify it's valid JPEG data (starts with JPEG magic bytes)
        assert decoded[:2] == b"\xff\xd8"

    def test_nonexistent_file_returns_none(self):
        """Test that nonexistent file returns None."""
        result = image_to_base64(Path("/nonexistent/path/image.png"))
        assert result is None


class TestFindImagesInDirectory:
    """Tests for find_images_in_directory function."""

    def test_finds_images_in_flat_directory(self, tmp_path: Path):
        """Test finding images in a flat directory."""
        (tmp_path / "image1.png").touch()
        (tmp_path / "image2.jpg").touch()
        (tmp_path / "document.txt").touch()

        images = find_images_in_directory(tmp_path)

        assert len(images) == 2
        names = [img.name for img in images]
        assert "image1.png" in names
        assert "image2.jpg" in names

    def test_finds_images_in_nested_directories(self, tmp_path: Path):
        """Test finding images in nested directories."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "root.png").touch()
        (subdir / "nested.jpg").touch()

        images = find_images_in_directory(tmp_path)

        assert len(images) == 2
        names = [img.name for img in images]
        assert "root.png" in names
        assert "nested.jpg" in names

    def test_respects_max_depth(self, tmp_path: Path):
        """Test that max_depth is respected."""
        # Create a deep directory structure
        # Structure: tmp_path/level0/image0.png, tmp_path/level0/level1/image1.png, etc.
        current = tmp_path
        for i in range(5):
            current = current / f"level{i}"
            current.mkdir()
            (current / f"image{i}.png").touch()

        # With max_depth=2, we scan: tmp_path(0) -> level0(1) -> level1(2)
        # Images at level0 (depth=1) and level1 (depth=2) should be found
        # level2 (depth=3) exceeds max_depth=2, so image2.png won't be found
        images = find_images_in_directory(tmp_path, max_depth=2)

        # Should find images at depth 1 and 2 (2 images)
        assert len(images) == 2
        names = [img.name for img in images]
        assert "image0.png" in names
        assert "image1.png" in names

    def test_returns_empty_for_nonexistent_directory(self):
        """Test that nonexistent directory returns empty list."""
        images = find_images_in_directory(Path("/nonexistent/path"))
        assert images == []

    def test_returns_sorted_list(self, tmp_path: Path):
        """Test that results are sorted."""
        (tmp_path / "z.png").touch()
        (tmp_path / "a.png").touch()
        (tmp_path / "m.png").touch()

        images = find_images_in_directory(tmp_path)

        names = [img.name for img in images]
        assert names == ["a.png", "m.png", "z.png"]


class TestProcessResultForImages:
    """Tests for process_result_for_images function."""

    def test_processes_screenshot_path_field(self, tmp_path: Path):
        """Test processing screenshot_path field."""
        img_path = tmp_path / "screenshot.png"
        create_test_image(img_path)

        result = {"success": True, "screenshot_path": str(img_path)}

        processed, images = process_result_for_images(result)

        assert len(images) == 1
        assert images[0]["source_field"] == "screenshot_path"
        assert images[0]["path"] == str(img_path)

    def test_processes_file_field(self, tmp_path: Path):
        """Test processing file field."""
        img_path = tmp_path / "capture.png"
        create_test_image(img_path)

        result = {"success": True, "file": str(img_path)}

        processed, images = process_result_for_images(result)

        assert len(images) == 1
        assert images[0]["source_field"] == "file"

    def test_processes_files_list_field(self, tmp_path: Path):
        """Test processing files list field."""
        img1 = tmp_path / "img1.png"
        img2 = tmp_path / "img2.png"
        create_test_image(img1, color=(255, 0, 0))
        create_test_image(img2, color=(0, 255, 0))

        result = {"success": True, "files": [str(img1), str(img2)]}

        processed, images = process_result_for_images(result)

        assert len(images) == 2

    def test_processes_output_dir_field(self, tmp_path: Path):
        """Test processing output_dir field."""
        create_test_image(tmp_path / "capture1.png")
        create_test_image(tmp_path / "capture2.jpg")
        (tmp_path / "readme.txt").write_bytes(b"text")

        result = {"success": True, "output_dir": str(tmp_path)}

        processed, images = process_result_for_images(result)

        assert len(images) == 2  # Only images, not txt

    def test_processes_screenshots_list_field(self, tmp_path: Path):
        """Test processing screenshots list field with filename key."""
        img1 = tmp_path / "shot1.png"
        img2 = tmp_path / "shot2.png"
        create_test_image(img1)
        create_test_image(img2)

        result = {
            "success": True,
            "screenshots": [
                {"camera": "front", "filename": str(img1)},
                {"camera": "back", "filename": str(img2)},
            ],
        }

        processed, images = process_result_for_images(result)

        assert len(images) == 2
        assert all(img["source_field"] == "screenshots[].filename" for img in images)

    def test_respects_size_limits(self, tmp_path: Path):
        """Test that size limits are respected."""
        # Create a larger image (500x500 will be several KB)
        large_img = tmp_path / "large.png"
        create_test_image(large_img, width=500, height=500)

        result = {"success": True, "screenshot_path": str(large_img)}

        # Set very small limits (smaller than a 500x500 JPEG)
        processed, images = process_result_for_images(
            result, max_image_size_mb=0.001  # ~1KB limit
        )

        # Large file should be skipped
        assert len(images) == 0

    def test_returns_original_result_unchanged(self, tmp_path: Path):
        """Test that original result dict is not modified."""
        img_path = tmp_path / "test.png"
        create_test_image(img_path)

        original = {"success": True, "screenshot_path": str(img_path)}
        original_copy = dict(original)

        processed, images = process_result_for_images(original)

        assert processed == original_copy  # Original data preserved
        assert "images" not in processed  # Not added by process_result_for_images

    def test_skips_nonexistent_paths(self):
        """Test that nonexistent paths are skipped."""
        result = {"success": True, "screenshot_path": "/nonexistent/image.png"}

        processed, images = process_result_for_images(result)

        assert len(images) == 0

    def test_skips_non_image_files(self, tmp_path: Path):
        """Test that non-image files are skipped."""
        txt_file = tmp_path / "document.txt"
        txt_file.write_bytes(b"text content")

        result = {"success": True, "file": str(txt_file)}

        processed, images = process_result_for_images(result)

        assert len(images) == 0

    def test_screenshots_field_skips_output_dir_scanning(self, tmp_path: Path):
        """Test that output_dir is NOT scanned when screenshots array is present.

        This prevents returning old/leftover images from the directory.
        Bug: editor_level_screenshot with 1 camera returned 4 images due to
        both screenshots[].filename AND output_dir directory scan being processed.
        """
        # Create explicit screenshot
        shot = tmp_path / "front.png"
        create_test_image(shot)

        # Create leftover files (simulating previous runs)
        create_test_image(tmp_path / "back.png")
        create_test_image(tmp_path / "Camera.png")

        # Result with BOTH screenshots array AND output_dir (like editor_level_screenshot)
        result = {
            "success": True,
            "screenshots": [
                {"camera": "front", "filename": str(shot)},
            ],
            "output_dir": str(tmp_path),  # Contains 3 images, but only 1 was requested
        }

        processed, images = process_result_for_images(result)

        # Should only return the explicit screenshot, NOT scan the whole directory
        assert len(images) == 1
        assert images[0]["source_field"] == "screenshots[].filename"
        assert "front.png" in images[0]["path"]
