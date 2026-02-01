---
name: threading-complete
description: Complete threading patterns for luma_tools including worker lifecycle, locks, imports, and lambda capture. Auto-loads when writing code that involves threading, workers, or async operations.
user-invocable: false
---

# Threading Patterns - Complete Reference

## Worker Pattern (CRITICAL)

### Using BaseTab Helper (Preferred)
```python
# Simple args
self.start_worker(
    my_function, arg1, arg2,
    on_result=self._handle_result,
    on_error=self._handle_error
)

# With keyword arguments - use worker_kwargs dict
self.start_worker(
    submit_job,
    worker_kwargs={"name": "MyJob", "priority": 50, "path": "/path"},
    on_result=self._on_submit_complete,
    on_error=self._on_submit_error,
    on_progress=self._on_progress  # Optional
)
```

### Manual Worker Pattern (When BaseTab unavailable)
```python
from ui_components import Worker  # LAZY IMPORT inside function

# Create worker
self._worker = Worker(func, arg1, arg2, kwarg1=value1)

# Connect ALL relevant signals
self._worker.signals.started.connect(self._on_started)
self._worker.signals.result.connect(self._handle_result)
self._worker.signals.error.connect(self._handle_error)
self._worker.signals.progress.connect(self._update_progress)
self._worker.signals.finished.connect(self._on_finished)

# Start on thread pool
QThreadPool.globalInstance().start(self._worker)
```

### WorkerSignals Available
- `started` - Emitted when worker begins
- `finished` - Emitted when worker completes (success or error)
- `error(str, str)` - Error message and traceback
- `result(object)` - Return value from function
- `progress(int, str)` - Percentage and message

### Progress Callback Pattern
If function signature includes `progress_callback`, Worker auto-injects it:
```python
def my_long_operation(data, progress_callback=None):
    for i, item in enumerate(data):
        process(item)
        if progress_callback:
            percent = int((i + 1) / len(data) * 100)
            progress_callback(percent, f"Processing {i + 1}/{len(data)}")
    return result
```

### Exception Handling in Workers
Worker functions should handle their own exceptions gracefully:
```python
def worker_func(items):
    results = []
    errors = []
    for item in items:
        try:
            result = process(item)
            results.append(result)
        except Exception as e:
            errors.append((item, str(e)))
    return {"results": results, "errors": errors}

# Handler can then report partial success
def _on_result(self, data):
    if data["errors"]:
        self.log(f"{len(data['errors'])} items failed")
    self.show_status(f"Processed {len(data['results'])} items")
```

## Worker Storage (CRITICAL - Prevents GC)

Workers MUST be stored on a long-lived object:
```python
# CORRECT - stored on self
self._worker = Worker(func)
self._scan_worker = Worker(scan_func)  # Use unique names for multiple workers

# WRONG - will be garbage collected before completion
worker = Worker(func)  # Lost when function returns!
```

For multiple concurrent workers:
```python
self._workers = []  # List for batch operations
for item in items:
    worker = Worker(process_item, item)
    worker.signals.result.connect(self._on_item_done)
    self._workers.append(worker)  # MUST store reference
    QThreadPool.globalInstance().start(worker)
```

## Lambda Capture in Loops (CRITICAL)

When creating lambdas/closures in loops, capture by value:
```python
# WRONG - all lambdas share same 'i' reference (always last value)
for i in range(5):
    button.clicked.connect(lambda: print(i))  # All print 4!

# CORRECT - capture 'i' by value using default argument
for i in range(5):
    button.clicked.connect(lambda x=i: print(x))  # Prints 0,1,2,3,4

# CORRECT - with worker in loop
for idx, item in enumerate(items):
    worker = Worker(process, item)
    worker.signals.result.connect(lambda r, i=idx: self._on_done(r, i))
    self._workers.append(worker)
```

## Lazy Imports for UI Components (CRITICAL)

UI components must be imported inside functions, not at module level:
```python
# WRONG - module-level import can block worker threads
from ui_components import Worker

class MyClass:
    def do_work(self):
        worker = Worker(...)

# CORRECT - lazy import inside function
class MyClass:
    def do_work(self):
        from ui_components import Worker  # Import here
        self._worker = Worker(...)
```

Exception: `StatusColors` enum is safe at module level (no Qt dependencies).

## Thread-Safe Caching with Locks

Any cache accessed from multiple threads needs a lock:
```python
import threading

class MyManager:
    def __init__(self):
        self._cache = {}
        self._cache_lock = threading.Lock()

    def get_cached(self, key):
        with self._cache_lock:
            return self._cache.get(key)

    def set_cached(self, key, value):
        with self._cache_lock:
            self._cache[key] = value

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()
```

Use `RLock` if same thread may acquire lock multiple times:
```python
self._lock = threading.RLock()  # Reentrant lock
```

## Never Update Qt Widgets from Workers

Workers run in background threads. Qt widgets are NOT thread-safe:
```python
# WRONG - will crash or corrupt state
def worker_func():
    self.ui.label.setText("Done")  # Qt call from worker thread!

# CORRECT - emit signal, update in slot
def worker_func():
    return "Done"  # Just return data

# In main thread (signal handler)
def _on_result(self, result):
    self.ui.label.setText(result)  # Safe - main thread
```

## app_state Thread Safety

`app_state` from `core.state_manager` is thread-safe (uses RLock internally):
```python
from core.state_manager import app_state

# Safe from any thread
app_state.jobname = "NewJob"
current = app_state.jobname
```

## Standard Error Handlers

Use BaseTab helpers for consistent error handling:
```python
def _on_operation_error(self, error_msg, traceback_str):
    self.on_worker_error(
        error_msg,
        traceback_str,
        status_prefix="MyOperation",
        show_dialog=True  # Optional error dialog
    )

def _on_operation_success(self, result):
    self.on_worker_success(
        "Operation complete!",
        status_message="Finished processing",
        log_message=f"Processed {len(result)} items"
    )
```

## Multiple Workers Pattern

For operations that need multiple concurrent workers:
```python
def start_batch_operation(self, items):
    self._pending_count = len(items)
    self._results = []
    self._batch_workers = []

    for item in items:
        worker = Worker(self._process_item, item)
        worker.signals.result.connect(self._on_item_complete)
        worker.signals.error.connect(self._on_item_error)
        self._batch_workers.append(worker)
        QThreadPool.globalInstance().start(worker)

def _on_item_complete(self, result):
    self._results.append(result)
    self._pending_count -= 1
    if self._pending_count == 0:
        self._on_batch_complete()
```

## Checklist Before Writing Threading Code

1. [ ] Worker stored on `self._worker` or `self._workers` list
2. [ ] UI component imports are lazy (inside function)
3. [ ] Lambdas in loops capture variables by value
4. [ ] Caches have threading.Lock protection
5. [ ] No Qt widget updates inside worker function
6. [ ] Error handlers connected to worker.signals.error
7. [ ] Progress callback in function signature if needed
