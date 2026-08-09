import inspect
import dataclasses
import importlib

from knowledge.lib02 import commands
from knowledge.lib02 import domain


def test_commands_are_frozen_dataclasses():
    assert dataclasses.is_dataclass(commands.ProgramNext)
    assert dataclasses.is_dataclass(commands.TrackNext)
    assert commands.ProgramNext.__dataclass_params__.frozen
    assert commands.TrackNext.__dataclass_params__.frozen


def test_continuity_capsule_routing_only():
    assert hasattr(domain.ContinuityCapsule, "routing_snapshots")
    fields = set(domain.ContinuityCapsule.__dataclass_fields__.keys())
    assert fields == {"routing_snapshots"}


def test_no_generic_update_object():
    mod = importlib.import_module("knowledge.lib02")
    assert not hasattr(mod, "UpdateObject")
