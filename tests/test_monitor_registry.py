import gc
from types import SimpleNamespace
from typing import get_args

import pytest

from src.rules.ability_monitors import (
    AbilityCooldownStartedMonitor,
    AbilityMonitorConfig,
    ChargeOfDarknessCooldownStartedMonitor,
)
from src.rules.item_monitors import (
    BkbCooldownStartedMonitor,
    BlinkCooldownStartedMonitor,
    BlinkMonitorConfig,
    CooldownReadyMonitor,
    CooldownStartedMonitor,
    ItemMonitorConfig,
    MidasMonitorConfig,
)
from src.rules.monitor_base import TargetedStatefulMonitor, monitor_class
from src.rules.monitor_config import MonitorType


@pytest.fixture(autouse=True)
def _drop_test_classes():
    """Monitor classes defined in a test stay in __subclasses__() until collected, and would
    break every later lookup; collect them once the test has returned."""
    yield
    gc.collect()
    assert monitor_class(MonitorType.ITEM, "COOLDOWN_READY") is CooldownReadyMonitor


@pytest.mark.parametrize("config, monitor", [
    (ItemMonitorConfig, MonitorType.ITEM),
    (BlinkMonitorConfig, MonitorType.ITEM),  # blink rules use the item classes for item_blink
    (MidasMonitorConfig, MonitorType.MIDAS),
    (AbilityMonitorConfig, MonitorType.ABILITY),
])
def test_every_config_event_has_a_class(config, monitor):
    for event in get_args(config.model_fields["event"].annotation):
        assert monitor_class(monitor, event)


def test_target_specific_class_wins_and_others_fall_back():
    assert monitor_class(MonitorType.ITEM, "COOLDOWN_STARTED", "item_blink") is BlinkCooldownStartedMonitor
    assert monitor_class(MonitorType.ITEM, "COOLDOWN_STARTED", "item_black_king_bar") is BkbCooldownStartedMonitor
    assert monitor_class(MonitorType.ITEM, "COOLDOWN_STARTED", "item_manta") is CooldownStartedMonitor
    assert monitor_class(MonitorType.ITEM, "COOLDOWN_READY", "item_blink") is CooldownReadyMonitor
    assert (
        monitor_class(MonitorType.ABILITY, "COOLDOWN_STARTED", "spirit_breaker_charge_of_darkness")
        is ChargeOfDarknessCooldownStartedMonitor
    )
    assert monitor_class(MonitorType.ABILITY, "COOLDOWN_STARTED", "spectre_reality") is AbilityCooldownStartedMonitor


def test_two_classes_declaring_the_same_event_are_refused():
    class Dup(TargetedStatefulMonitor):
        for_type = MonitorType.ITEM
        for_event = "COOLDOWN_READY"

        def evaluate(self, snap):
            pass

    with pytest.raises(AssertionError, match="both declare"):
        monitor_class(MonitorType.ITEM, "COOLDOWN_READY")


def test_targeted_monitor_without_event_asserts():
    class Missing(TargetedStatefulMonitor):
        def evaluate(self, snap):
            pass

    rule = SimpleNamespace(id="r", monitor=SimpleNamespace(target="item_manta"))
    with pytest.raises(AssertionError, match="must set for_type"):
        Missing(rule, bus=None)
    with pytest.raises(AssertionError, match="must set for_type"):
        Missing.declared_for()


def test_subclass_that_changes_no_field_asserts():
    class Variant(CooldownReadyMonitor):
        pass

    with pytest.raises(AssertionError, match="same for_type, for_event and for_target as CooldownReadyMonitor"):
        Variant.declared_for()
