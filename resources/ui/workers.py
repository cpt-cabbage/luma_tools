"""
Threading utilities for background operations.

Provides QThread workers for running functions without blocking the GUI.
"""
import logging
import traceback
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, Slot

logger = logging.getLogger(__name__)


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

        # Only add progress_callback if the function accepts it.
        # inspect.signature raises ValueError/TypeError for some builtins and
        # C functions — treat those as "no progress support" instead of
        # failing the Worker constructor.
        import inspect
        try:
            sig = inspect.signature(fn)
        except (ValueError, TypeError):
            sig = None
        if sig is not None and 'progress_callback' in sig.parameters:
            # Replace progress_callback with signal emitter if present
            if 'progress_callback' in self.kwargs:
                del self.kwargs['progress_callback']
            self.kwargs['progress_callback'] = self.signals.progress.emit

    @Slot()
    def run(self):
        """Execute the worker function with error handling.

        All signal emits are guarded against `RuntimeError: Signal source has
        been deleted`, which happens when the QApplication is torn down
        (e.g. during shutdown) while a worker is still mid-flight.
        """
        def _safe_emit(signal, *args):
            try:
                signal.emit(*args)
            except RuntimeError:
                pass  # QObject already destroyed (app shutting down)

        try:
            _safe_emit(self.signals.started)
            result = self.fn(*self.args, **self.kwargs)
            _safe_emit(self.signals.result, result)
        except Exception as e:
            error_msg = str(e)
            tb = traceback.format_exc()
            _safe_emit(self.signals.error, error_msg, tb)
            logger.error(f"Worker error: {error_msg}")
            logger.error(tb)
        finally:
            _safe_emit(self.signals.finished)


def start_worker_thread(func, *args, on_result=None, on_error=None, on_progress=None, worker_kwargs=None):
    """
    Create, connect signals, and start a Worker on the global thread pool.

    Returns the Worker instance. Caller MUST store the returned worker on a
    long-lived object (e.g. self._worker) to prevent garbage collection.

    Args:
        func: Function to run in background thread
        *args: Positional arguments for the function
        on_result: Callback for successful completion (receives result)
        on_error: Callback for errors (receives error_msg, traceback_str)
        on_progress: Callback for progress updates (receives int, str)
        worker_kwargs: Dict of keyword arguments for the function

    Returns:
        Worker: The started worker instance
    """
    if worker_kwargs:
        worker = Worker(func, *args, **worker_kwargs)
    else:
        worker = Worker(func, *args)

    if on_result:
        worker.signals.result.connect(on_result)
    if on_error:
        worker.signals.error.connect(on_error)
    if on_progress:
        worker.signals.progress.connect(on_progress)

    QThreadPool.globalInstance().start(worker)
    return worker
