import threading


# A class for thread-safe access to a variable
class AtomicValue:
    def __init__(self, initial=None):
        self.__value = initial
        self.__lock = threading.Lock()

    def get(self):
        self.__lock.acquire()
        result = self.__value
        self.__lock.release()
        return result

    def set(self, value):
        self.__lock.acquire()
        self.__value = value
        self.__lock.release()
