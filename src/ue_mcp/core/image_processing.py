"""Image processing utilities for Claude AI clients.

This module provides utilities to convert image file paths to base64-encoded
data for MCP clients that support image display (like Claude AI).
"""

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Client name that triggers base64 image conversion
CLAUDE_AI_CLIENT_NAME = "claude-ai"

# Image extensions to process
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}

# Fields that contain image paths (field_name -> field_type)
# field_type: "single" = single path string, "list" = list of path strings, "directory" = directory path
IMAGE_PATH_FIELDS: dict[str, str] = {
    "screenshot_path": "single",  # editor_asset_inspect
    "file": "single",  # editor_capture_window (window mode)
    "files": "list",  # editor_capture_window (batch mode)
    "output_dir": "directory",  # editor_capture_pie, editor_trace_actors_in_pie
}

# For list fields where each item is a dict with a key containing the path
# field_name -> key_name
SCREENSHOT_LIST_FIELDS: dict[str, str] = {
    "screenshots": "filename",  # editor_level_screenshot
}

# Size limits
DEFAULT_MAX_IMAGE_SIZE_MB = 10.0
DEFAULT_MAX_TOTAL_SIZE_MB = 50.0


def is_claude_ai_client(client_name: str | None) -> bool:
    """Check if the client is Claude AI (exact match for 'claude-ai').

    Args:
        client_name: The MCP client name from InitializeRequest

    Returns:
        True if client is Claude AI, False otherwise
    """
    return client_name == CLAUDE_AI_CLIENT_NAME


def is_image_file(path: Path) -> bool:
    """Check if a file is an image based on extension.

    Args:
        path: Path to the file

    Returns:
        True if file has an image extension
    """
    return path.suffix.lower() in IMAGE_EXTENSIONS


def find_images_in_directory(dir_path: Path, max_depth: int = 3) -> list[Path]:
    """Find all image files in a directory up to max_depth.

    Args:
        dir_path: Directory to search
        max_depth: Maximum recursion depth (default: 3)

    Returns:
        Sorted list of image file paths
    """
    images: list[Path] = []
    if not dir_path.exists() or not dir_path.is_dir():
        return images

    def scan(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            for item in current.iterdir():
                if item.is_file() and is_image_file(item):
                    images.append(item)
                elif item.is_dir():
                    scan(item, depth + 1)
        except PermissionError:
            pass

    scan(dir_path, 0)
    return sorted(images)


def image_to_base64(path: Path) -> dict[str, Any] | None:
    """Convert an image file to base64.

    Args:
        path: Path to the image file

    Returns:
        Dict with path, data, mime_type, size_bytes, or None if failed
    """
    try:
        if not path.exists():
            return None

        size_bytes = path.stat().st_size
        mime_type = mimetypes.guess_type(str(path))[0] or "image/png"

        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")

        return {
            "path": str(path),
            "data": data,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
        }
    except Exception as e:
        logger.warning(f"Failed to convert image {path}: {e}")
        return None


def process_result_for_images(
    result: dict[str, Any],
    max_image_size_mb: float = DEFAULT_MAX_IMAGE_SIZE_MB,
    max_total_size_mb: float = DEFAULT_MAX_TOTAL_SIZE_MB,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Process a result dict and extract/convert images to base64.

    Scans the result dict for known image path fields and converts them
    to base64-encoded data.

    Args:
        result: Tool result dictionary
        max_image_size_mb: Maximum size for a single image in MB
        max_total_size_mb: Maximum total size for all images in MB

    Returns:
        Tuple of (original result dict, list of image data dicts)
    """
    images: list[dict[str, Any]] = []
    total_size = 0
    max_image_bytes = int(max_image_size_mb * 1024 * 1024)
    max_total_bytes = int(max_total_size_mb * 1024 * 1024)

    def add_image(path: Path, source_field: str) -> bool:
        """Add an image to the list if within size limits."""
        nonlocal total_size
        if not path.exists():
            return False

        size = path.stat().st_size
        if size > max_image_bytes:
            logger.warning(
                f"Image {path} exceeds size limit ({size} > {max_image_bytes})"
            )
            return False
        if total_size + size > max_total_bytes:
            logger.warning(f"Total size limit exceeded, skipping {path}")
            return False

        img_data = image_to_base64(path)
        if img_data:
            img_data["source_field"] = source_field
            images.append(img_data)
            total_size += size
            return True
        return False

    # Process single/list/directory fields
    for field, field_type in IMAGE_PATH_FIELDS.items():
        if field not in result:
            continue

        value = result[field]
        if field_type == "single" and isinstance(value, str):
            path = Path(value)
            if path.exists() and is_image_file(path):
                add_image(path, field)

        elif field_type == "list" and isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    path = Path(item)
                    if path.exists() and is_image_file(path):
                        add_image(path, field)

        elif field_type == "directory" and isinstance(value, str):
            dir_path = Path(value)
            for img_path in find_images_in_directory(dir_path):
                add_image(img_path, field)

    # Process screenshot list fields (e.g., screenshots[].filename)
    for field, key in SCREENSHOT_LIST_FIELDS.items():
        if field not in result:
            continue

        items = result[field]
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and key in item:
                    path = Path(item[key])
                    if path.exists() and is_image_file(path):
                        add_image(path, f"{field}[].{key}")

    return result, images
