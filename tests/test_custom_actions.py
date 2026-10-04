"""Unit tests that execute actions/actions.py without requiring a running Rasa server.

Minimal rasa_sdk stand-ins are injected only when the SDK is unavailable in the
local authoring environment. Inside Docker, the real Rasa SDK is used instead.
"""
from __future__ import annotations

import importlib
import os
import sys
import types


def _install_rasa_sdk_stubs():
    if "rasa_sdk" in sys.modules:
        return
    sdk = types.ModuleType("rasa_sdk")
    events = types.ModuleType("rasa_sdk.events")
    executor = types.ModuleType("rasa_sdk.executor")

    class Action:
        pass

    class Tracker:
        pass

    class SlotSet(dict):
        def __init__(self, key, value):
            super().__init__(event="slot", name=key, value=value)

    class CollectingDispatcher:
        pass

    sdk.Action = Action
    sdk.Tracker = Tracker
    events.SlotSet = SlotSet
    executor.CollectingDispatcher = CollectingDispatcher
    sys.modules["rasa_sdk"] = sdk
    sys.modules["rasa_sdk.events"] = events
    sys.modules["rasa_sdk.executor"] = executor


try:
    import rasa_sdk  # noqa: F401
except ModuleNotFoundError:
    _install_rasa_sdk_stubs()

mod = importlib.import_module("actions.actions")


class FakeDispatcher:
    def __init__(self):
        self.messages = []

    def utter_message(self, **kwargs):
        self.messages.append(kwargs)


class FakeTracker:
    def __init__(self, slots=None, text="hello", events=None):
        self.slots = slots or {}
        self.latest_message = {"text": text}
        self.events = events or [{"event": "user", "text": text}]
        self.sender_id = "test-user"

    def get_slot(self, key):
        return self.slots.get(key)


def test_search_action_returns_ranked_payload(monkeypatch):
    monkeypatch.delenv("AMADEUS_BASE_URL", raising=False)
    dispatcher = FakeDispatcher()
    tracker = FakeTracker({"destination": "Berlin", "budget": 800, "sustainability_level": "eco"})
    events = mod.ActionSearchTravelOptions().run(dispatcher, tracker, {})
    assert events == []
    payloads = [m.get("json_message", {}) for m in dispatcher.messages]
    eco = next(p["eco_options"] for p in payloads if "eco_options" in p)
    assert eco["destination"] == "Berlin"
    assert eco["transport"]
    assert eco["data_status"] == "demo_fallback"


def test_carbon_action_fails_transparently_without_key(monkeypatch):
    monkeypatch.delenv("CLIMATIQ_API_KEY", raising=False)
    dispatcher = FakeDispatcher()
    tracker = FakeTracker({"origin": "Amsterdam", "destination": "Berlin", "travel_mode": "rail"})
    mod.ActionCalculateCarbon().run(dispatcher, tracker, {})
    custom = next(m["json_message"]["carbon_result"] for m in dispatcher.messages if m.get("json_message"))
    assert custom["verified_live"] is False
    assert custom["source"] == "unavailable"


def test_first_fallback_returns_constrained_buttons():
    dispatcher = FakeDispatcher()
    tracker = FakeTracker({"fallback_count": 0}, text="unclear request")
    events = mod.ActionDefaultFallback().run(dispatcher, tracker, {})
    assert dispatcher.messages[0]["buttons"]
    assert events[0]["name"] == "fallback_count"
    assert events[0]["value"] == 1


def test_second_fallback_escalates_with_context():
    dispatcher = FakeDispatcher()
    tracker = FakeTracker({"fallback_count": 1, "destination": "Berlin"}, text="still unclear")
    events = mod.ActionDefaultFallback().run(dispatcher, tracker, {})
    handover = next(m["json_message"]["handover"] for m in dispatcher.messages if m.get("json_message"))
    assert handover["active"] is True
    assert handover["context"]["slots"]["destination"] == "Berlin"
    assert events[0]["value"] == 0


def test_handover_action_limits_context_to_relevant_slots():
    dispatcher = FakeDispatcher()
    tracker = FakeTracker(
        {"destination": "Berlin", "budget": 900, "fallback_count": 1, "unrelated": "secret"},
        text="human please",
    )
    mod.ActionHumanHandover().run(dispatcher, tracker, {})
    handover = next(m["json_message"]["handover"] for m in dispatcher.messages if m.get("json_message"))
    assert handover["context"]["slots"]["destination"] == "Berlin"
    assert "fallback_count" not in handover["context"]["slots"]
    assert "unrelated" not in handover["context"]["slots"]
