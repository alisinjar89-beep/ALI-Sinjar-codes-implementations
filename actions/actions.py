from __future__ import annotations

import os
from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

from .services import (
    AmadeusLegacyClient,
    ClimatiqClient,
    DemoTravelProvider,
    ProviderError,
    build_handover_context,
    city_iata,
    normalise_amadeus_flights,
    normalise_amadeus_hotels,
    rank_options,
)


class ActionSearchTravelOptions(Action):
    def name(self) -> Text:
        return "action_search_travel_options"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        destination = tracker.get_slot("destination") or "selected destination"
        origin = tracker.get_slot("origin") or os.getenv("DEMO_ORIGIN", "Amsterdam")
        start_date = tracker.get_slot("start_date")
        level = tracker.get_slot("sustainability_level") or "balanced"
        budget = tracker.get_slot("budget")

        provider_status = "demo_fallback"
        source_note = (
            "Demonstration inventory is shown because authorised live travel inventory is unavailable. "
            "Demonstration carbon and price values are illustrative and are never labelled as verified live claims."
        )
        data = DemoTravelProvider().options(destination)

        amadeus = AmadeusLegacyClient()
        origin_code, destination_code = city_iata(origin), city_iata(destination)
        if amadeus.enabled and origin_code and destination_code and start_date:
            try:
                flight_records = amadeus.search_flights(origin_code, destination_code, str(start_date))
                hotel_records = amadeus.search_hotels_by_city(destination_code)
                approximate_air_carbon = None
                try:
                    approximate_air_carbon = ClimatiqClient().estimate_distance_travel(origin, destination, "air")["co2e"]
                except ProviderError:
                    pass
                live_transport = normalise_amadeus_flights(flight_records, approximate_air_carbon)
                live_hotels = normalise_amadeus_hotels(hotel_records)
                if live_transport or live_hotels:
                    data = {
                        "transport": live_transport or data["transport"],
                        "hotels": live_hotels or data["hotels"],
                        "activities": data["activities"],
                    }
                    provider_status = "authorised_live_inventory"
                    source_note = (
                        "Authorised travel inventory is retrieved through the configured Amadeus-compatible endpoint. "
                        "Hotel sustainability claims remain unverified unless an independent certification source confirms them."
                    )
            except ProviderError as exc:
                source_note += f" Live inventory failed safely: {str(exc)[:120]}."

        ranked_transport = rank_options(data["transport"], level)
        ranked_hotels = rank_options(data["hotels"], level)
        dispatcher.utter_message(
            text=f"Options for {destination} are ranked using carbon impact, price, and the {level} preference profile. {source_note}"
        )
        dispatcher.utter_message(
            json_message={
                "eco_options": {
                    "destination": destination,
                    "budget": budget,
                    "transport": ranked_transport,
                    "hotels": ranked_hotels,
                    "activities": data["activities"],
                    "data_status": provider_status,
                    "source_note": source_note,
                }
            }
        )
        return []


class ActionCalculateCarbon(Action):
    def name(self) -> Text:
        return "action_calculate_carbon"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        origin = tracker.get_slot("origin") or os.getenv("DEMO_ORIGIN", "Amsterdam")
        destination = tracker.get_slot("destination") or "Berlin"
        mode = tracker.get_slot("travel_mode") or "rail"
        try:
            result = ClimatiqClient().estimate_distance_travel(origin, destination, mode)
            dispatcher.utter_message(
                text=(
                    f"Climatiq estimates approximately {result['co2e']:.1f} {result['unit']}CO2e for one passenger travelling "
                    f"one way from {origin} to {destination} by {mode}. The estimate supports comparison rather than exact accounting."
                )
            )
            dispatcher.utter_message(
                json_message={
                    "carbon_result": {
                        "source": "Climatiq Travel API",
                        "verified_live": True,
                        "kg_co2e": round(result["co2e"], 2),
                        "distance_km": result.get("distance_km"),
                        "mode": mode,
                    }
                }
            )
        except ProviderError as exc:
            dispatcher.utter_message(
                text="A live carbon estimate is unavailable because the carbon provider is not configured or responding. No demonstration number is presented as live evidence."
            )
            dispatcher.utter_message(json_message={"carbon_result": {"source": "unavailable", "verified_live": False, "reason": str(exc)}})
        return []


class ActionHumanHandover(Action):
    def name(self) -> Text:
        return "action_human_handover"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        context = build_handover_context(
            tracker.sender_id,
            dict(tracker.slots),
            tracker.latest_message.get("text", "") or "",
            tracker.events,
        )
        dispatcher.utter_message(
            text="The planning case is marked for human review. Relevant trip preferences and recent conversation context are packaged for continuity."
        )
        dispatcher.utter_message(json_message={"handover": {"active": True, "context": context, "display": "Human advisor handover active"}})
        return []


class ActionDefaultFallback(Action):
    """Two-stage fallback: constrained clarification, then context-preserving handover."""

    def name(self) -> Text:
        return "action_default_fallback"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        count = int(tracker.get_slot("fallback_count") or 0)
        if count < 1:
            dispatcher.utter_message(
                text="That request is unclear. Choose the closest option so the conversation can recover safely.",
                buttons=[
                    {"title": "Plan a trip", "payload": "/plan_trip"},
                    {"title": "Compare carbon", "payload": "/ask_carbon"},
                    {"title": "Find hotels", "payload": "/ask_hotels"},
                    {"title": "Human advisor", "payload": "/request_handover"},
                ],
            )
            return [SlotSet("fallback_count", 1)]

        context = build_handover_context(
            tracker.sender_id,
            dict(tracker.slots),
            tracker.latest_message.get("text", "") or "",
            tracker.events,
        )
        dispatcher.utter_message(
            text="The request remains ambiguous after clarification, so the conversation is escalated with its existing context."
        )
        dispatcher.utter_message(
            json_message={"handover": {"active": True, "context": context, "display": "Human advisor handover active after fallback"}}
        )
        return [SlotSet("fallback_count", 0)]
