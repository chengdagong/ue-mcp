"""Image processing utilities for Claude AI clients.

This module provides utilities to convert image file paths to base64-encoded
data for MCP clients that support image display (like Claude AI).
"""

import base64
import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image

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

# JPEG compression settings
MAX_COMPRESSED_SIZE_BYTES = 1 * 1024 * 1024  # 1MB max for compressed images
JPEG_INITIAL_QUALITY = 85  # Start with high quality
JPEG_MIN_QUALITY = 20  # Don't go below this quality
JPEG_QUALITY_STEP = 10  # Reduce quality by this amount each iteration


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


def image_to_base64(
    path: Path,
    max_size_bytes: int = MAX_COMPRESSED_SIZE_BYTES,
) -> dict[str, Any] | None:
    """Convert an image file to base64 JPEG, compressing if necessary.

    Converts all image formats to JPEG and compresses to stay under max_size_bytes.
    Uses iterative quality reduction to achieve target size.

    Args:
        path: Path to the image file
        max_size_bytes: Maximum size for the compressed image (default: 1MB)

    Returns:
        Dict with path, data, mime_type, size_bytes, or None if failed
    """
    try:
        if not path.exists():
            return None

        original_size = path.stat().st_size

        # Load image with Pillow
        with Image.open(path) as img:
            # Convert RGBA to RGB (JPEG doesn't support alpha)
            if img.mode in ("RGBA", "LA", "P"):
                # Create white background for transparency
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Try to compress to target size
            quality = JPEG_INITIAL_QUALITY
            jpeg_data = None

            while quality >= JPEG_MIN_QUALITY:
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                jpeg_data = buffer.getvalue()

                if len(jpeg_data) <= max_size_bytes:
                    break

                quality -= JPEG_QUALITY_STEP

            if jpeg_data is None:
                logger.warning(f"Failed to compress image {path}")
                return None

            compressed_size = len(jpeg_data)
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

            logger.info(
                f"Compressed {path.name}: {original_size / 1024:.1f}KB -> "
                f"{compressed_size / 1024:.1f}KB ({compression_ratio:.1f}% reduction, quality={quality})"
            )

            # Encode to base64
            data = base64.standard_b64encode(jpeg_data).decode("utf-8")

            return {
                "path": str(path),
                "data": data,
                "mime_type": "image/jpeg",
                "size_bytes": compressed_size,
                "original_size_bytes": original_size,
                "compression_quality": quality,
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

    # Track if screenshot list fields were processed (have explicit file lists)
    screenshot_fields_processed: set[str] = set()

    # Process screenshot list fields FIRST (e.g., screenshots[].filename)
    # These provide explicit file lists, so we don't need directory scanning
    for field, key in SCREENSHOT_LIST_FIELDS.items():
        if field not in result:
            continue

        items = result[field]
        if isinstance(items, list) and items:
            screenshot_fields_processed.add(field)
            for item in items:
                if isinstance(item, dict) and key in item:
                    path = Path(item[key])
                    if path.exists() and is_image_file(path):
                        add_image(path, f"{field}[].{key}")

    # Process single/list/directory fields
    for field, field_type in IMAGE_PATH_FIELDS.items():
        if field not in result:
            continue

        # Skip output_dir directory scanning if screenshots were already processed
        # (tools with explicit file lists don't need directory scanning)
        if field == "output_dir" and field_type == "directory" and screenshot_fields_processed:
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

    return result, images
