
import re
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


_USERNAME_RE = re.compile(r'^[a-zA-Z0-9._-]+$')


def is_valid_username(username) -> bool:
    """Validate a username contains only safe filesystem characters.

    Used for path-construction safety: blocks traversal attempts like '../foo'.
    Allowed: alphanumerics, dot, underscore, hyphen.
    """
    if not username or not isinstance(username, str):
        return False
    username = username.strip()
    if not username:
        return False
    if not _USERNAME_RE.match(username):
        return False
    # Reject pure-dot names ("." / "..") — they pass the character class but
    # are path components that traverse instead of naming a folder
    if set(username) == {'.'}:
        return False
    return True


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


def version_sort_key(name):
    """Sort key that orders version-suffixed names numerically.

    Plain string sort puts "v9" AFTER "v10", so latest-version pickers chose
    the wrong folder for unpadded version names. Names without a number sort
    first (never chosen as "latest" over a numbered version).

    Example:
        >>> sorted(["shot_v9", "shot_v10", "shot_v2"], key=version_sort_key)
        ['shot_v2', 'shot_v9', 'shot_v10']
    """
    version = get_trailing_number(name)
    return (int(version) if version is not None else -1, name)


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
    if not path:
        return path
    return path.replace("\\", "/")


def ensure_directory(path):
    """
    Ensure directory exists, create if it doesn't.

    Args:
        path: Directory path to ensure exists
    """
    os.makedirs(path, exist_ok=True)


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


_MISSING = object()


def load_json(path, default=_MISSING):
    """
    Load JSON file with error handling.

    Args:
        path: Path to JSON file
        default: Default value if file doesn't exist or fails to load

    Returns:
        Loaded JSON data or default value
    """
    if not os.path.exists(path):
        return {} if default is _MISSING else default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading JSON from {path}: {e}")
        return {} if default is _MISSING else default


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

    Strips only the trailing `.<frame>.<ext>` (or `.####.<ext>`) segments so
    dotted version names survive — the previous `split(".")[0]` truncated
    "scene_v1.2.0001.exr" to "scene_v1".

    This handles common sequence naming patterns:
    - Simple: "render_name.0001.exr" -> "render_name"
    - With padding: "render_name.####.exr" -> "render_name"
    - Dotted versions: "scene_v1.2.0001.exr" -> "scene_v1.2"

    Args:
        filename: Filename or basename to extract render name from
        strip_frame_padding: Kept for backwards compatibility — padding
                           markers (####) are always stripped now.

    Returns:
        str: The render name (filename minus extension and frame segment)

    Example:
        >>> extract_render_name("beauty_v001.0042.exr")
        'beauty_v001'
        >>> extract_render_name("beauty_v001.####.exr", strip_frame_padding=True)
        'beauty_v001'
        >>> extract_render_name("scene_v1.2.0001.exr")
        'scene_v1.2'
    """
    parts = [p for p in filename.split(".") if p != ""]
    if not parts:
        return filename.strip(".")

    # Drop a trailing extension (any segment containing a letter: exr, mp4, ...)
    if len(parts) > 1 and any(c.isalpha() for c in parts[-1]):
        parts = parts[:-1]

    # Drop at most ONE trailing frame segment (digits or #### padding) so a
    # dotted version number before the frame is preserved
    if len(parts) > 1 and (parts[-1].isdigit() or all(c == '#' for c in parts[-1])):
        parts = parts[:-1]

    return ".".join(parts)


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
    from .config import FFMPEG_PATH
    from .subprocess_utils import run_command

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
            result = run_command(cmd, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logger.debug(f"FFprobe duration extraction failed: {e}")

    # Fallback to FFmpeg
    try:
        cmd = [FFMPEG_PATH, '-i', file_path]
        result = run_command(cmd, timeout=5)
        output = result.stderr
        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)', output)
        if match:
            hours, minutes, seconds, centiseconds = map(int, match.groups())
            return hours * 3600 + minutes * 60 + seconds + centiseconds / 100.0
    except Exception as e:
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


def format_elapsed_time(seconds):
    """Format elapsed time in a compact human-readable way.

    Unlike format_duration() which uses colon notation (2:05),
    this uses compact notation (2m 5s) suitable for progress messages.

    Args:
        seconds: Duration in seconds (float or int)

    Returns:
        str: Formatted time ("30s", "2m 30s", "1h 5m")
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"
