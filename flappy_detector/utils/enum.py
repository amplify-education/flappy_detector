"""Store enums"""
from enum import Enum


class Ec2State(Enum):
    """EC2 Instance States"""

    TERMINATED = "terminated", -1
    RUNNING = "running", 1

    def __new__(cls, *args, **_):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    def __init__(self, _: str, change: int = 0):
        self.change = change

    def __str__(self):
        return str(self.value)
