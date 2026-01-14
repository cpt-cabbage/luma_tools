"""
Threading utilities for background operations.

Provides QThread workers for running functions without blocking the GUI.
"""
import traceback
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, Slot
from PySide6.QtWidgets import QApplication


class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Signals:
        started: Emitted when the worker starts
        finished: Emitted when the worker finishes successfully
        error: Emitted when an error occurs (str: error message, str: traceback)
        result: Emitted with the result of the operation (object: result)
        progress: Emitted with progress updates (int: percentage, str: message)
    """
    started = Signal()
    finished = Signal()
    error = Signal(str, str)  # error message, traceback
    result = Signal(object)   # result data
    progress = Signal(int, str)  # progress percentage, message


class Worker(QRunnable):
    """
    Generic worker thread for running functions in the background.

    This prevents blocking the GUI thread and keeps spinners smooth.

    Usage:
        worker = Worker(some_function, arg1, arg2, kwarg1=value1)
        worker.signals.result.connect(handle_result)
        worker.signals.error.connect(handle_error)
        worker.signals.progress.connect(update_progress)
        QThreadPool.globalInstance().start(worker)
    """

    def __init__(self, fn, *args, **kwargs):
        """
        Initialize the worker.

        Args:
            fn: The function to run in the background
            *args: Positional arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
                     Note: 'progress_callback' kwarg will be replaced with signal emitter
        """
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Only add progress_callback if the function accepts it
        import inspect
        sig = inspect.signature(fn)
        if 'progress_callback' in sig.parameters:
            # Replace progress_callback with signal emitter if present
            if 'progress_callback' in self.kwargs:
                del self.kwargs['progress_callback']
            self.kwargs['progress_callback'] = self.signals.progress.emit

    @Slot()
    def run(self):
        """Execute the worker function with error handling."""
        try:
            self.signals.started.emit()
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
            self.signals.finished.emit()
        except Exception as e:
            error_msg = str(e)
            tb = traceback.format_exc()
            self.signals.error.emit(error_msg, tb)
            print(f"Worker error: {error_msg}")
            print(tb)


class ThreadedOperation(QObject):
    """
    Helper class to manage threaded operations with proper cleanup.

    Usage:
        operation = ThreadedOperation(function, arg1, arg2)
        operation.signals.result.connect(handle_result)
        operation.signals.error.connect(handle_error)
        operation.start()
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.worker = Worker(fn, *args, **kwargs)
        self.signals = self.worker.signals

    def start(self):
        """Start the operation on a background thread."""
        QThreadPool.globalInstance().start(self.worker)


def report_progress(callback, progress, message):
    """
    Report progress and process Qt events to keep UI responsive.

    This is a utility function to consolidate the common pattern of:
    - Checking if callback exists
    - Calling the callback
    - Processing Qt events to keep the UI responsive

    Args:
        callback: Progress callback function(progress, message) or None
        progress: Progress value (0-100)
        message: Status message string

    Example:
        report_progress(progress_callback, 50, "Halfway done...")
    """
    if callback:
        callback(progress, message)
        QApplication.processEvents()
