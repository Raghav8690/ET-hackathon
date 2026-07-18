"""
PS8 – Local Document File Storage Service
Handles saving uploaded file streams to the local filesystem under
`<project_root>/data/uploads/`.  Creates date-based subdirectories to avoid
flat directory bloat.
Contract
--------
- ``save_upload(filename, file_stream) -> str``  returns the absolute file path.
- ``get_upload_dir() -> Path``  returns the configured uploads root.
- ``delete_upload(filepath) -> bool``  removes a file from disk.
"""
import os
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
# ---------------------------------------------------------------------------
# Resolve uploads directory (relative to project root)
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[2]  # backend/services/file_storage.py → project root
UPLOADS_DIR = _project_root / "data" / "uploads"
def get_upload_dir() -> Path:
    """Return the base uploads directory, creating it if needed."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADS_DIR
def _generate_safe_filename(original_filename: str) -> str:
    """Generate a unique, collision-free filename preserving the extension.
    Format: ``<uuid4>_<sanitised_original>``
    """
    # Keep the original extension
    ext = Path(original_filename).suffix.lower()
    # Sanitise the stem (remove problematic characters)
    stem = Path(original_filename).stem
    safe_stem = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in stem)
    # Prepend a short UUID to guarantee uniqueness
    unique_prefix = uuid.uuid4().hex[:12]
    return f"{unique_prefix}_{safe_stem}{ext}"
def _get_date_subdir() -> Path:
    """Create and return a date-based subdirectory (YYYY/MM/DD)."""
    now = datetime.now(timezone.utc)
    subdir = UPLOADS_DIR / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir
def save_upload(
    original_filename: str,
    file_stream: BinaryIO,
    *,
    use_date_subdir: bool = True,
) -> dict:
    """Save an uploaded file stream to the local filesystem.
    Parameters
    ----------
    original_filename : str
        The original name of the uploaded file.
    file_stream : BinaryIO
        A binary file-like object (e.g. ``UploadFile.file``).
    use_date_subdir : bool
        If ``True`` (default), files are stored under ``YYYY/MM/DD`` sub-dirs.
    Returns
    -------
    dict
        ``{"filepath": str, "filename": str, "file_size_bytes": int}``
    """
    get_upload_dir()  # Ensure base dir exists
    if use_date_subdir:
        dest_dir = _get_date_subdir()
    else:
        dest_dir = UPLOADS_DIR
    safe_name = _generate_safe_filename(original_filename)
    dest_path = dest_dir / safe_name
    # Stream the content to disk in chunks (memory-efficient for large files)
    file_size = 0
    with open(dest_path, "wb") as f:
        while True:
            chunk = file_stream.read(1024 * 1024)  # 1 MB chunks
            if not chunk:
                break
            f.write(chunk)
            file_size += len(chunk)
    return {
        "filepath": str(dest_path),
        "filename": safe_name,
        "file_size_bytes": file_size,
    }
def delete_upload(filepath: str) -> bool:
    """Delete a file from the uploads directory.
    Returns ``True`` if the file was removed, ``False`` if it didn't exist.
    """
    path = Path(filepath)
    if path.exists() and path.is_file():
        path.unlink()
        return True
    return False
def file_exists(filepath: str) -> bool:
    """Check whether a file exists at the given path."""
    return Path(filepath).is_file()
