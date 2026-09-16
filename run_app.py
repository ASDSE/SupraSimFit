import multiprocessing

from gui.main_window import launch

if __name__ == '__main__':
    # A packaged build re-executes this file to start each worker process. Without
    # this call the worker would launch a second copy of the application instead,
    # and each copy would do the same again.
    multiprocessing.freeze_support()
    launch()
