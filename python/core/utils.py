
import re
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_trailing_number(s):
    """
    Extract the last number from a string.

    Args:
        s: String potentially containing numbers

    Returns:
        str: The last number found as a string, or None if no digits found

    Example:
        >>> get_trailing_number("render_v003")
        '003'
        >>> get_trailing_number("no_numbers")
        None
    """
    matches = re.findall(r'\d+', s)
    return matches[-1] if matches else None


def truncate_at_suffix(string, suffix):
    """
    Truncate string at the end of the suffix, keeping everything up to and including it.

    Args:
        string: Input string
        suffix: Substring to find and truncate at (suffix is kept in result)

    Returns:
        str: String truncated at end of suffix (e.g., "hello_world_test" -> "hello_world")

    Raises:
        ValueError: If suffix is not found in string

    Example:
        >>> truncate_at_suffix("hello_world_test", "_world")
        'hello_world'
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


def validate_file_exists(path, raise_error=True):
    """
    Validate that a file exists.

    Args:
        path: Path to validate
        raise_error: If True, raise FileNotFoundError; otherwise return False

    Returns:
        bool: True if file exists

    Raises:
        FileNotFoundError: If file doesn't exist and raise_error is True
    """
    if not os.path.exists(path):
        if raise_error:
            raise FileNotFoundError(f"File not found: {path}")
        return False
    return True


def validate_is_file(path, raise_error=True):
    """
    Validate that path is a file (not a directory).

    Args:
        path: Path to validate
        raise_error: If True, raise ValueError; otherwise return False

    Returns:
        bool: True if path is a file

    Raises:
        ValueError: If path is not a file and raise_error is True
    """
    if not os.path.isfile(path):
        if raise_error:
            raise ValueError(f"Path is not a file: {path}")
        return False
    return True


def validate_is_directory(path, raise_error=True):
    """
    Validate that path is a directory.

    Args:
        path: Path to validate
        raise_error: If True, raise ValueError; otherwise return False

    Returns:
        bool: True if path is a directory

    Raises:
        ValueError: If path is not a directory and raise_error is True
    """
    if not os.path.isdir(path):
        if raise_error:
            raise ValueError(f"Path is not a directory: {path}")
        return False
    return True


def ensure_directory(path):
    """
    Ensure directory exists, create if it doesn't.

    Args:
        path: Directory path to ensure exists
    """
    os.makedirs(path, exist_ok=True)


def safe_remove(path, log_errors=False):
    """
    Safely remove a file, ignoring errors if it doesn't exist.

    Args:
        path: Path to file to remove
        log_errors: If True, log warnings on failure

    Returns:
        bool: True if file was removed, False otherwise
    """
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except Exception as e:
        if log_errors:
            logger.warning(f"Could not remove {path}: {e}")
    return False


def safe_rmtree(path, log_errors=False):
    """
    Safely remove a directory tree, ignoring errors.

    Args:
        path: Path to directory to remove
        log_errors: If True, log warnings on failure

    Returns:
        bool: True if directory was removed, False otherwise
    """
    import shutil
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
            return True
    except Exception as e:
        if log_errors:
            logger.warning(f"Could not remove directory {path}: {e}")
    return False


def replace_frame_tokens(template, frame_num):
    """
    Replace <STARTFRAME%N> tokens with actual frame numbers.

    Deadline uses <STARTFRAME%{padding}> format where N is the zero-padding width.
    Example: <STARTFRAME%4> with frame_num=42 becomes "0042"

    Args:
        template: String with frame tokens like <STARTFRAME%4>
        frame_num: Frame number to substitute

    Returns:
        str: String with tokens replaced by zero-padded frame numbers
    """
    return re.sub(r'<STARTFRAME%(\d+)>',
                  lambda m: f"{frame_num:0{m.group(1)}d}", template)


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
    dirname = os.path.dirname(path)
    if dirname:
        ensure_directory(dirname)
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
            except Exception as cleanup_err:
                logger.debug(f"Could not remove temp file {temp_path}: {cleanup_err}")
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
    total = 0
    for f in folder_path.rglob('*'):
        try:
            total += f.stat().st_size
        except (PermissionError, FileNotFoundError, OSError):
            pass
    return ByteSize(total)


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


# ============================================================================
# PATH VALIDATION HELPERS
# ============================================================================

def validate_directory_for_operation(path, operation="access"):
    """
    Check if directory exists and log error if not.

    Args:
        path: Directory path to validate
        operation: Description of operation for error message (e.g., "scan", "write")

    Returns:
        bool: True if directory exists, False otherwise
    """
    if not path:
        logger.error(f"Cannot {operation}: path is empty or None")
        return False
    if not os.path.isdir(path):
        logger.error(f"Cannot {operation}: directory does not exist: {path}")
        return False
    return True


def validate_file_for_operation(path, operation="access"):
    """
    Check if file exists and log error if not.

    Args:
        path: File path to validate
        operation: Description of operation for error message (e.g., "read", "process")

    Returns:
        bool: True if file exists, False otherwise
    """
    if not path:
        logger.error(f"Cannot {operation}: path is empty or None")
        return False
    if not os.path.isfile(path):
        logger.error(f"Cannot {operation}: file does not exist: {path}")
        return False
    return True


def safe_list_dir(path, pattern=None):
    """
    Safely list directory contents with error handling.

    Args:
        path: Directory to list
        pattern: Optional glob pattern to filter (e.g., "*.png")

    Returns:
        list: List of filenames, empty list on error
    """
    if not path or not os.path.isdir(path):
        return []
    try:
        if pattern:
            import fnmatch
            return [f for f in os.listdir(path) if fnmatch.fnmatch(f, pattern)]
        return os.listdir(path)
    except OSError as e:
        logger.warning(f"Error listing directory {path}: {e}")
        return []


# ============================================================================
# USER MESSAGE FORMATTING
# ============================================================================

def plural(count, singular, plural_form=None):
    """
    Return count with singular or plural form based on count.

    Args:
        count: Number of items
        singular: Singular form of the word (e.g., "item")
        plural_form: Optional plural form (default: singular + "s")

    Returns:
        str: Formatted string like "1 item" or "5 items"

    Example:
        >>> plural(1, "file")
        '1 file'
        >>> plural(5, "file")
        '5 files'
        >>> plural(2, "match", "matches")
        '2 matches'
    """
    if plural_form is None:
        plural_form = singular + "s"
    return f"{count} {singular if count == 1 else plural_form}"


# ============================================================================
# NESTED DICT UTILITIES
# ============================================================================

def nested_get(d, keys, default=None):
    """
    Safely get a nested dictionary value.

    Args:
        d: Dictionary to traverse
        keys: List of keys to traverse (e.g., ['a', 'b', 'c'] for d['a']['b']['c'])
        default: Value to return if any key is missing

    Returns:
        Value at nested path, or default if not found

    Example:
        >>> d = {'a': {'b': {'c': 42}}}
        >>> nested_get(d, ['a', 'b', 'c'])
        42
        >>> nested_get(d, ['a', 'x'], 'default')
        'default'
    """
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        if key not in current:
            return default
        current = current[key]
    return current


def nested_set(d, keys, value):
    """
    Set a nested dictionary value, creating intermediate dicts as needed.

    Args:
        d: Dictionary to modify
        keys: List of keys for the path (e.g., ['a', 'b', 'c'])
        value: Value to set at the path

    Example:
        >>> d = {}
        >>> nested_set(d, ['a', 'b', 'c'], 42)
        >>> d
        {'a': {'b': {'c': 42}}}
    """
    current = d
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def nested_delete(d, keys):
    """
    Delete a nested dictionary value if it exists.

    Args:
        d: Dictionary to modify
        keys: List of keys for the path

    Returns:
        bool: True if value was deleted, False if path didn't exist

    Example:
        >>> d = {'a': {'b': {'c': 42}}}
        >>> nested_delete(d, ['a', 'b', 'c'])
        True
        >>> d
        {'a': {'b': {}}}
    """
    current = d
    for key in keys[:-1]:
        if not isinstance(current, dict) or key not in current:
            return False
        current = current[key]
    if isinstance(current, dict) and keys[-1] in current:
        del current[keys[-1]]
        return True
    return False


# ============================================================================
# Media Duration Utilities
# ============================================================================

def get_media_duration(file_path):
    """
    Extract duration from video or audio file using FFprobe or FFmpeg.

    Args:
        file_path: Path to video or audio file

    Returns:
        float: Duration in seconds, or None if duration cannot be determined

    Example:
        >>> duration = get_media_duration("video.mp4")
        >>> duration
        125.5
        >>> format_duration(duration)
        '2:05'
    """
    from core.config import FFMPEG_PATH
    import subprocess

    if not FFMPEG_PATH or not os.path.exists(file_path):
        return None

    # Try FFprobe first (cleaner output)
    ffprobe_path = FFMPEG_PATH.replace('ffmpeg.exe', 'ffprobe.exe')
    if os.path.exists(ffprobe_path):
        try:
            cmd = [
                ffprobe_path,
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=creationflags)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, Exception) as e:
            logger.debug(f"FFprobe duration extraction failed: {e}")

    # Fallback to FFmpeg
    try:
        cmd = [FFMPEG_PATH, '-i', file_path]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=creationflags)
        # FFmpeg outputs duration in stderr
        output = result.stderr
        # Parse "Duration: HH:MM:SS.ms" format
        import re
        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)', output)
        if match:
            hours, minutes, seconds, centiseconds = map(int, match.groups())
            return hours * 3600 + minutes * 60 + seconds + centiseconds / 100.0
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"FFmpeg duration extraction failed: {e}")

    return None


def format_duration(seconds):
    """
    Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds (float or int)

    Returns:
        str: Formatted duration ("MM:SS" for < 1 hour, "H:MM:SS" for >= 1 hour)

    Example:
        >>> format_duration(125.5)
        '2:05'
        >>> format_duration(3725)
        '1:02:05'
        >>> format_duration(45)
        '0:45'
    """
    if seconds is None or seconds < 0:
        return "0:00"

    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"
