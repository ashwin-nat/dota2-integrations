from enum import Enum, auto


class EventCode(Enum):
    # Ingress
    INCOMING_DATA = auto()      # raw GSI payload received from HTTP

    # State lifecycle
    STATE_UPDATED = auto()

    # Day / Night events
    DAYTIME_STARTED = auto()
    NIGHTTIME_STARTED = auto()
