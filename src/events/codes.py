from enum import Enum, auto


class EventCode(Enum):
    # State lifecycle
    STATE_UPDATED = auto()

    # Midas events
    MIDAS_CHARGED = auto()       # one charge gained (0 -> 1)
    MIDAS_OVERCHARGED = auto()   # two charges stacked (any -> 2)
