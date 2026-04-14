---
name: check-code
description: Pattern verification for luma_tools code. Checks threading, imports, settings, and over-engineering. Run automatically after writing code, report only if issues found.
user-invocable: false
---

# Code Pattern Verification

After writing code, I MUST verify it against these patterns. Check all categories in parallel, report by severity. Only report if issues found.

## Category 1: Threading (CRITICAL)

### Worker Storage
Check: Any `Worker(` creation must be stored on `self._worker` or similar.

```python
# ISSUE: Worker not stored (will be GC'd)
worker = Worker(func)
QThreadPool.globalInstance().start(worker)

# CORRECT
self._worker = Worker(func)
```

### Lambda Closures in Loops
Check: Any lambda inside a for/while loop must capture variables by value.

```python
# ISSUE: Variable captured by reference
for i in items:
    button.clicked.connect(lambda: handle(i))

# CORRECT: Capture by value
for i in items:
    button.clicked.connect(lambda x=i: handle(x))
```

### Cache Thread Safety
Check: Any `self._cache = {}` or similar dict used across threads needs a lock.

```python
# ISSUE: No lock on shared cache
self._cache[key] = value

# CORRECT
with self._cache_lock:
    self._cache[key] = value
```

### Qt Widget Access from Workers
Check: Worker functions must NOT access Qt widgets directly.

```python
# ISSUE: Widget access in worker
def worker_func():
    self.ui.label.setText("Done")  # WRONG

# CORRECT: Return data, update in handler
def worker_func():
    return "Done"
def on_result(result):
    self.ui.label.setText(result)
```

### BaseTab.start_worker with kwargs
Check: Use `worker_kwargs` dict for keyword arguments, not positional args.

```python
# ISSUE: Passing kwargs as positional
self.start_worker(submit_job, name, priority, path, on_result=handler)

# CORRECT: Use worker_kwargs
self.start_worker(
    submit_job,
    worker_kwargs={"name": name, "priority": priority, "path": path},
    on_result=handler
)
```

### Multiple Concurrent Workers
Check: If a class needs multiple concurrent workers, use descriptive names.

```python
# ISSUE: Single _worker overwritten
self._worker = Worker(load_func)
self._worker = Worker(save_func)  # Overwrites previous!

# CORRECT: Descriptive names
self._load_worker = Worker(load_func)
self._save_worker = Worker(save_func)
```

## Category 2: Imports (HIGH)

### Lazy Imports for UI Components
Check: `from ui_components import` or `from workers import` must be inside functions, not at module level.

```python
# ISSUE: Module-level UI import
from ui_components import Worker

class MyClass:
    def method(self):
        worker = Worker(...)

# CORRECT: Lazy import
class MyClass:
    def method(self):
        from ui_components import Worker
        self._worker = Worker(...)
```

Exception: `StatusColors` enum is safe at module level.

### Correct Import Paths
Check: Imports use correct paths per PYTHONPATH setup.

```python
# Core modules
from core.config import UIColors
from core.state_manager import app_state
from core.settings_manager import safe_get_setting

# UI modules (resources/ui/ in PYTHONPATH)
from ui_components import Worker  # Inside function
from dialog_helpers import confirm_action
```

## Category 3: Settings (MEDIUM)

### Settings Registry
Check: Any new setting key used with get_setting/set_setting must be in SETTINGS_REGISTRY.

```python
# ISSUE: Setting not registered
value = get_setting("my_new_setting")  # Will raise KeyError

# CORRECT: Add to SETTINGS_REGISTRY first
# In core/settings_manager.py:
SETTINGS_REGISTRY = {
    "my_new_setting": SettingDef("my_new_setting", default=False, scope="user"),
}
```

### Safe Accessors
Check: Prefer safe_get_setting/safe_set_setting to avoid exceptions.

```python
# BETTER: Won't raise KeyError
value = safe_get_setting("my_setting", False)
safe_set_setting("my_setting", True)
```

## Category 4: Over-Engineering (MEDIUM)

### Unnecessary Abstractions
Check: Don't create helpers/utilities for one-time operations.

```python
# ISSUE: Over-abstracted for single use
def _create_button_handler(action):
    return lambda: self._handle_action(action)

# CORRECT: Direct implementation
button.clicked.connect(lambda: self._do_action())
```

### Premature Generalization
Check: Don't design for hypothetical future requirements.

```python
# ISSUE: Future-proofing not requested
def process(data, format="json", version=1, backwards_compat=True):
    ...

# CORRECT: Only what's needed now
def process(data):
    ...
```

### Unnecessary Comments/Docstrings
Check: Don't add docstrings to code I didn't change unless the logic is non-obvious.

## Category 5: Gallery-Specific (if applicable)

### Incremental Display
Check: Gallery updates use `incremental=True` to avoid flashing.

```python
# ISSUE: Will flash/clear
self._manager.display_items(items, view_mode)

# CORRECT
self._manager.display_items(items, view_mode, incremental=True)
```

### Manager Coordination
Check: Gallery operations go through appropriate managers, not direct widget manipulation.

## Category 6: State Manager (if applicable)

### Thread-Safe Property Access
Check: Use `app_state` properties, don't access internal attributes directly.

```python
# ISSUE: Accessing internal state
if app_state._is_admin:  # WRONG

# CORRECT: Use property
if app_state.is_admin:
```

### Role Checking
Check: Use appropriate role check for the feature.

```python
# For admin-only features (Settings tab)
if app_state.is_admin:

# For elevated access (currently equivalent to is_admin)
if app_state.has_elevated_access:
```

Supervisor role was removed. Do not introduce `is_sup` or supervisor-only paths.

## Category 7: Event Bus (if applicable)

### Signal Connections
Check: Event bus connections happen in `initialize()`, not repeatedly.

```python
# ISSUE: Connected in method called multiple times
def refresh(self):
    pipeline_events.job_completed.connect(self._on_job)  # Multiple connections!

# CORRECT: Connect once in initialize
def initialize(self):
    pipeline_events.job_completed.connect(self._on_job)
```

### Available Signals
Common event bus signals to use:
- `job_submitted(job_id, expected_count, prefix)` - ComfyUI job started
- `job_progress(job_id, percent, message)` - Job progress update
- `job_completed(job_id, output_paths)` - Job finished successfully
- `job_failed(job_id, error_message)` - Job failed
- `all_jobs_completed(total_outputs, elapsed_seconds)` - Batch complete
- `selection_changed(paths, count)` - Gallery selection changed

## Report Format

If issues found, report as:

```
## Code Verification Issues

### Critical
- **[file.py:42]** Worker not stored on self - will be garbage collected
- **[file.py:78]** Lambda in loop captures by reference

### High
- **[file.py:15]** UI component import at module level - should be lazy

### Medium
- **[file.py:95]** New setting 'my_setting' not in SETTINGS_REGISTRY
```

If no issues: Report nothing (silent success).

## When to Run

- After writing any new code
- After modifying existing code
- Before presenting code to user

Run checks in parallel, organize results by severity, provide file:line references.
