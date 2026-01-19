
import re
import os
from pathlib import Path


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
        self.teraabytes = self.TB = self / self._KB**4
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
        print(f"Error scanning EXR sequences in {path}: {e}")
        return []
