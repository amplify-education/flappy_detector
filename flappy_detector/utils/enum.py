from enum import Enum


class Ec2State(Enum):
    TERMINATED = "terminated", -1
    RUNNING = "running", 1

    def __new__(cls, *args, **kwds):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    def __init__(self, _: str, change: int = None):
        self.change = change

    def __str__(self):
        return self.value
