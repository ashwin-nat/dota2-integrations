from .hero import HeroState, parse_hero
from .items import Items, parse_items
from .map import MapState, parse_map
from .player import PlayerState, parse_player


class GameState:
    def __init__(self):
        self._version: int = 0
        self.items: Items | None = None
        self.map: MapState | None = None
        self.player: PlayerState | None = None
        self.hero: HeroState | None = None

        # Rule-engine state — populated by set_compiled_rules()
        from src.rules.compiler import CompiledRules
        self._compiled_rules: CompiledRules | None = None
        self._prev_items: Items | None = None
        self._prev_hero: HeroState | None = None

    def set_compiled_rules(self, compiled_rules) -> None:
        """Attach precompiled rule monitors. Called once at startup."""
        self._compiled_rules = compiled_rules

    def set(self, data: dict):
        # This method is synchronous. Only CPU-bound operations (parsing, diffing,
        # state comparisons) belong here. For I/O-bound work such as playing sounds
        # or controlling lights, monitors must emit an event onto RuleEventBus and
        # let ActionExecutor handle it asynchronously.
        self._version += 1

        items = data.get("items")
        player = data.get("player")
        hero = data.get("hero")
        map = data.get("map")

        self.items = parse_items(items) if items else None
        self.player = parse_player(player) if player else None
        self.hero = parse_hero(hero) if hero else None
        new_map = parse_map(map) if map else None
        self._handle_match_change(new_map)
        self.map = new_map
        self._run_rule_monitors()

    def version(self) -> int:
        return self._version

    def _handle_match_change(self, new_map: MapState | None) -> None:
        old_id = self.map.matchid if self.map else None
        new_id = new_map.matchid if new_map else None
        if new_id != old_id:
            self._clear_monitors()
            self._prev_items = None
            self._prev_hero = None
            print(f"Match changed from {old_id} to {new_id}")

    def _clear_monitors(self) -> None:
        if self._compiled_rules:
            for m in self._compiled_rules.item_monitors:
                m.clear()
            for m in self._compiled_rules.map_monitors:
                m.clear()
            for m in self._compiled_rules.hero_monitors:
                m.clear()

    def _run_rule_monitors(self) -> None:
        if not self._compiled_rules:
            return

        if self.map:
            for monitor in self._compiled_rules.map_monitors:
                monitor.evaluate(self.map)

        if self.items:
            for monitor in self._compiled_rules.item_monitors:
                monitor.evaluate(self.items, self._prev_items)
            self._prev_items = self.items

        if self.hero:
            for monitor in self._compiled_rules.hero_monitors:
                monitor.evaluate(self.hero)
            self._prev_hero = self.hero
