# Core Module

Core utilities and infrastructure for Luma Tools.

## Module Reference

### utils.py — Common Helpers
- `ensure_directory(path)` - create directory if needed (prefer over `os.makedirs`)
- `load_json(path, default)` / `save_json(path, data)` - with error handling and atomic writes
- `normalize_path(path)` - Windows backslash → forward slash for AYON/Deadline
- `extract_render_name(filename, strip_frame_padding=False)` - extract render name from sequence filename

### error_handling.py — Error Handling Utilities
- `@safe_operation(name, return_on_error)` - decorator for functions that may fail
- `with handle_errors(name, reraise=False)` - context manager for error blocks
- `log_error(operation, error, variable)` - consistent error logging format

### caching.py — Reusable Caching Patterns
- `@cached_with_ttl(seconds)` - decorator for time-based cache invalidation
- `ThreadSafeCache(max_size)` - thread-safe dictionary cache with optional size limit

### metadata_file.py — Thread-Safe JSON Metadata Files
- `MetadataFile(directory, filename)` - class for JSON files with mtime-based caching
- `get_metadata_file(directory, filename)` - factory for reusing MetadataFile instances

### config.py — Configuration Constants
- `UIColors` - background, text, accent, status colors, `GROUP_COLORS` for gallery groups
- `UIStyles` - reusable stylesheet snippets
- `OIIO_PATH`, `FFMPEG_PATH` - tool paths

### import_utils.py — Graceful Optional Imports
- `safe_import()`, `safe_import_multiple()` - imports with `*_AVAILABLE` flags

### subprocess_utils.py — Subprocess Execution (Windows-compatible)
- `run_command(cmd, capture_output, text, timeout, cwd, shell)` - execute command, return CompletedProcess
- `run_command_with_result(cmd, log_prefix, timeout)` - execute command, return (success, stdout, stderr) tuple
- `start_process(cmd, cwd, stdout, stderr, text, encoding, env)` - start long-running process

### logging_utils.py — Centralized Logging
- `get_network_output_path()` - get network path from global settings (cached)
- `get_network_log_dir(subdirectory)` - get network log directory with fallback
- `get_local_log_dir()` - get local fallback directory (~/.luma_tools/logs/)
- `clear_path_cache()` - clear cached paths after settings changes
- `TeeStream` - stream that writes to both original stream and logging function
- `TeeWriter` - stream that writes timestamped lines to log file and console
- `setup_file_logging(log_prefix, subdirectory, include_hostname, include_username, redirect_stdout, tee_mode)` - setup file logging
- `cleanup_old_logs(log_dir, prefix, keep_count)` - remove old log files
- `setup_exception_hook()` - install global exception handler
