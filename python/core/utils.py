
import re
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_trailing_number(s):
    """
    Extract trailing number from string.

    Args:
        s: String containing a number at the end

    Returns:
        str: The trailing number as a string

    Example:
        >>> get_trailing_number("render_v003")
        '003'
    """
    query = s
    return re.findall(r'\d+', query)[-1]


def remove_after(string, suffix):
    """
    Remove everything after (and including) the suffix.

    Args:
        string: Input string
        suffix: Suffix to find

    Returns:
        str: String up to and including the suffix
    """
    return string[:string.index(suffix) + len(suffix)]


def substring_after(s, delim):
    """
    Get substring after delimiter.

    Args:
        s: Input string
        delim: Delimiter to search for

    Returns:
        str: Everything after the delimiter
    """
    return s.partition(delim)[2]


def normalize_path(path):
    """
    Normalize path to use forward slashes (for AYON/Deadline compatibility).

    Args:
        path: Windows-style path with backslashes

    Returns:
        str: Path with forward slashes
    """
    return path.replace("\\", "/")


def ensure_directory(path):
    """
    Ensure directory exists, create if it doesn't.

    Args:
        path: Directory path to ensure exists
    """
    os.makedirs(path, exist_ok=True)


def remove_prefix(s, prefix):
    """
    Remove prefix from string (Python <3.9 compatible).

    Args:
        s: Input string
        prefix: Prefix to remove

    Returns:
        str: String with prefix removed if present
    """
    if hasattr(s, 'removeprefix'):
        return s.removeprefix(prefix)
    return s[len(prefix):] if s.startswith(prefix) else s


def remove_suffix(s, suffix):
    """
    Remove suffix from string (Python <3.9 compatible).

    Args:
        s: Input string
        suffix: Suffix to remove

    Returns:
        str: String with suffix removed if present
    """
    if hasattr(s, 'removesuffix'):
        return s.removesuffix(suffix)
    return s[:-len(suffix)] if suffix and s.endswith(suffix) else s


def load_json(path, default=None):
    """
    Load JSON file with error handling.

    Args:
        path: Path to JSON file
        default: Default value if file doesn't exist or fails to load

    Returns:
        Loaded JSON data or default value
    """
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading JSON from {path}: {e}")
        return default if default is not None else {}


def save_json(path, data, pretty=True):
    """
    Save JSON file with atomic write to prevent corruption.

    Args:
        path: Path to save JSON file
        data: Data to save
        pretty: If True, format with indentation (default: True)

    Returns:
        bool: True if successful, False otherwise
    """
    ensure_directory(os.path.dirname(path))
    temp_path = path + ".tmp"
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2 if pretty else None)
        os.replace(temp_path, path)
        return True
    except Exception as e:
        logger.warning(f"Error saving JSON to {path}: {e}")
        # Clean up temp file if it exists
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


def get_folder_size(folder):
    """
    Calculate total size of folder recursively.

    Args:
        folder: Path to folder (str or Path)

    Returns:
        ByteSize: Formatted size object
    """
    folder_path = Path(folder)
    return ByteSize(sum(file.stat().st_size for file in folder_path.rglob('*')))


class ByteSize(int):
    """
    Format byte sizes into human-readable form.

    Usage:
        >>> size = ByteSize(1024 * 1024 * 500)  # 500 MB
        >>> print(size)
        500.00 MB
        >>> size.GB
        0.48828125
    """

    _KB = 1024
    _suffixes = 'B', 'KB', 'MB', 'GB', 'TB'

    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, *args, **kwargs)

    def __init__(self, *args, **kwargs):
        self.bytes = self.B = int(self)
        self.kilobytes = self.KB = self / self._KB**1
        self.megabytes = self.MB = self / self._KB**2
        self.gigabytes = self.GB = self / self._KB**3
        self.terabytes = self.TB = self / self._KB**4
        *suffixes, last = self._suffixes
        suffix = next((
            suffix
            for suffix in suffixes
            if 1 < getattr(self, suffix) < self._KB
        ), last)
        self.readable = suffix, getattr(self, suffix)
        super().__init__()

    def __str__(self):
        return self.__format__('.2f')

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, super().__repr__())

    def __format__(self, format_spec):
        suffix, val = self.readable
        return '{val:{fmt}} {suf}'.format(val=val, fmt=format_spec, suf=suffix)

    def __sub__(self, other):
        return self.__class__(super().__sub__(other))

    def __add__(self, other):
        return self.__class__(super().__add__(other))

    def __mul__(self, other):
        return self.__class__(super().__mul__(other))

    def __rsub__(self, other):
        return self.__class__(super().__sub__(other))

    def __radd__(self, other):
        return self.__class__(super().__add__(other))

    def __rmul__(self, other):
        return self.__class__(super().__rmul__(other))


def pad_frame_number(frame_number, padding=4):
    """
    Pad frame number with leading zeros.

    Args:
        frame_number: Frame number to pad
        padding: Number of digits (default: 4)

    Returns:
        str: Padded frame number

    Example:
        >>> pad_frame_number(42, 4)
        '0042'
    """
    return str(frame_number).zfill(padding)


def update_path_version(path, new_version):
    """
    Update version number in a path string.

    This function finds version patterns like '_v001', '_v002', etc. in a path
    and replaces them with the new version number.

    Args:
        path: Path string containing a version number (e.g., '/path/to/render_v001')
        new_version: New version number (int)

    Returns:
        str: Updated path with new version number

    Example:
        >>> update_path_version('/render/shot_v003/file.exr', 5)
        '/render/shot_v005/file.exr'
    """
    return re.sub(r'_v\d{3}', f'_v{new_version:03d}', path)


def scan_exr_sequences(path):
    """
    Scan a directory for EXR image sequences using fileseq.

    Args:
        path: Directory path to scan for EXR sequences

    Returns:
        list: List of fileseq.FileSequence objects found in the directory

    Example:
        >>> sequences = scan_exr_sequences('/path/to/renders')
        >>> for seq in sequences:
        ...     print(seq)
    """
    try:
        import fileseq
        search_pattern = os.path.join(path, "*.exr")
        return list(fileseq.findSequencesOnDisk(search_pattern))
    except Exception as e:
        logger.error(f"Error scanning EXR sequences in {path}: {e}")
        return []


def extract_render_name(filename, strip_frame_padding=False):
    """
    Extract render name from a sequence filename.

    This handles common sequence naming patterns:
    - Simple: "render_name.0001.exr" -> "render_name"
    - With padding: "render_name.####.exr" -> "render_name"

    Args:
        filename: Filename or basename to extract render name from
        strip_frame_padding: If True, also strips frame padding markers (####)
                           from the result. Use this for fileseq basenames.

    Returns:
        str: The render name (first part before dots)

    Example:
        >>> extract_render_name("beauty_v001.0042.exr")
        'beauty_v001'
        >>> extract_render_name("beauty_v001.####.exr", strip_frame_padding=True)
        'beauty_v001'
    """
    if strip_frame_padding:
        # Handle fileseq basenames with #### padding markers
        parts = [p for p in filename.split('.') if p and not all(c == '#' for c in p)]
        return parts[0] if parts else filename.replace("#", "").strip(".")
    else:
        # Simple extraction - just get first part before any dot
        return filename.split(".")[0]
