class GameState:
    def __init__(self):
        self._data: dict | None = None
        self._version: int = 0

    def get(self) -> dict | None:
        return self._data

    def set(self, data: dict):
        # store a copy to avoid accidental mutation
        self._data = data.copy()
        self._version += 1

    def version(self) -> int:
        return self._version
