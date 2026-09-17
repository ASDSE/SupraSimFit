import multiprocessing

if __name__ == '__main__':
    # A packaged build re-executes this file to start each worker process. Without
    # this call the worker would launch a second copy of the application instead,
    # and each copy would do the same again.
    multiprocessing.freeze_support()

    # The order is load-bearing: freeze_support() returns only in the process the
    # user started, so importing the interface after it keeps a worker process
    # from loading Qt at all.
    from gui.main_window import launch

    launch()
