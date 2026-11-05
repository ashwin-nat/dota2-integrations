import logging

from src.lighting.arbiter import LightingArbiter
from src.rules.bus import EventBus
from src.rules.compiler import CompiledRules
from src.rules.monitor_base import StateSnapshot
from .abilities import Abilities, parse_abilities
from .hero import HeroState, parse_hero
from .items import Items, parse_items
from .map import MapState, parse_map
from .player import PlayerState, parse_player

logger = logging.getLogger(__name__)


class GameState:
    def __init__(self, compiled_rules: CompiledRules, bus: EventBus, light_arbiter: LightingArbiter):
        self._version: int = 0
        self.raw: dict | None = None  # latest payload as received, for the /state debug endpoint
        self.items: Items | None = None
        self.abilities: Abilities | None = None
        self.map: MapState | None = None
        self.player: PlayerState | None = None
        self.hero: HeroState | None = None

        self._compiled_rules = compiled_rules
        self._bus = bus  # stamped with game/clock time so emitted events carry it
        self._light_arbiter = light_arbiter  # committed once per processed update
        self._prev_items: Items | None = None
        self._abilities_logged: bool = False

    def update(self, data: dict):
        # This method is synchronous. Only CPU-bound operations (parsing, diffing,
        # state comparisons) belong here. For I/O-bound work such as playing sounds
        # or controlling lights, monitors must emit an event onto the EventBus and
        # let the action executors handle it (their workers run the async parts).
        self._version += 1
        self.raw = data

        items = data.get("items")
        abilities = data.get("abilities")
        player = data.get("player")
        hero = data.get("hero")
        map = data.get("map")

        if not map:
            return

        game_state = map.get("game_state")
        if game_state != "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS":
            logger.info(f"Ignoring update: game state is {game_state}")
            return

        self.items = parse_items(items) if items else None
        self.abilities = parse_abilities(abilities) if abilities else None
        self.player = parse_player(player) if player else None
        self.hero = parse_hero(hero) if hero else None
        new_map = parse_map(map) if map else None
        self._handle_match_change(new_map)
        self.map = new_map
        self._log_abilities_once()
        self._bus.game_time = new_map.game_time
        self._bus.clock_time = new_map.clock_time
        snap = StateSnapshot(
            items=self.items,
            prev_items=self._prev_items,
            abilities=self.abilities,
            hero=self.hero,
            player=self.player,
            map=self.map,
        )
        self._compiled_rules.evaluate_all(snap)
        if self.items is not None:
            self._prev_items = self.items
        self._light_arbiter.commit()

    def set_compiled_rules(self, compiled_rules: CompiledRules) -> None:
        """Swap in freshly compiled rules (config reload). New monitors start with empty state."""
        self._compiled_rules = compiled_rules

    def version(self) -> int:
        return self._version

    def events(self) -> dict:
        """Debug view of the bus: total events published and, in --debug mode, the most recent ones (oldest first)."""
        return {
            "enabled": self._bus.history is not None,
            "published": self._bus.published,
            "recent": [
                {"key": e.key, "type": e.type.value, "game_time": e.game_time, "clock_time": e.clock_time}
                for e in (self._bus.history or ())
            ],
        }

    def _handle_match_change(self, new_map: MapState | None) -> None:
        old_id = self.map.matchid if self.map else None
        new_id = new_map.matchid if new_map else None
        if new_id != old_id:
            self._compiled_rules.clear_all()
            self._light_arbiter.clear_all()
            self._prev_items = None
            self._abilities_logged = False
            logger.info(f"Match changed from {old_id} to {new_id}")

    def _log_abilities_once(self) -> None:
        if self._abilities_logged or not self.abilities:
            return
        lines = "\n".join(f"  {a.name}" for a in self.abilities)
        logger.info(f"Hero abilities:\n{lines}")
        self._abilities_logged = True
