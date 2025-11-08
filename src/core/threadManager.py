from PySide6.QtCore import QThread, QObject, Signal, Slot, QMutex

class WorkerSignals(QObject):
    finished = Signal()
    result = Signal(object)
    error = Signal(Exception)

class Worker(QObject):
    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.function(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(e)
        finally:
            self.signals.finished.emit()

class ThreadManager:
    def __init__(self):
        self.threads = []
        self.mutex = QMutex()

    def _safe_remove_thread(self, thread, worker):
        self.mutex.lock()
        try:
            # Check if thread still exists in the list before removing
            thread_tuple = (thread, worker)
            if thread_tuple in self.threads:
                self.threads.remove(thread_tuple)
        finally:
            self.mutex.unlock()

    def run_function(self, function, *args, **kwargs):
        # Create thread and worker
        thread = QThread()
        worker = Worker(function, *args, **kwargs)
        worker.moveToThread(thread)

        # Connect signals
        thread.started.connect(worker.run)
        worker.signals.finished.connect(thread.quit)
        worker.signals.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        
        # Use a safe remove method if thread is already removed
        thread.finished.connect(lambda t=thread, w=worker: self._safe_remove_thread(t, w))

        # Store thread reference with mutex protection
        self.mutex.lock()
        try:
            self.threads.append((thread, worker))
        finally:
            self.mutex.unlock()

        # Start thread
        thread.start()
        return worker.signals

    def cleanup(self):
        self.mutex.lock()
        try:
            # Create a copy of the threads list to iterate over
            threads_copy = self.threads[:]
        finally:
            self.mutex.unlock()
        
        # Quit all running threads
        for thread, _ in threads_copy:
            if thread.isRunning():
                thread.quit()
                thread.wait(1000)
        
        # Clear the list with mutex protection
        self.mutex.lock()
        try:
            self.threads.clear()
        finally:
            self.mutex.unlock()