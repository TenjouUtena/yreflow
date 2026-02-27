from enum import Enum


class State(Enum):
    NEW = 1
    AUTH = 2       # WebSocket open, version sent, awaiting response
    LOGIN = 3      # Version received, auth.auth.login sent (password mode)
    SUBSCRIBE = 4
    CON = 5
