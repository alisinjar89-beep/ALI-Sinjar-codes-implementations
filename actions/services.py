"""Service and scoring layer for Eco-Travel Advisor.

External providers remain isolated behind adapters so Rasa actions stay testable.
The Amadeus Self-Service portal is no longer generally available, therefore its
adapter is opt-in and never labels demonstration inventory as live provider data.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests

ROOT = Path(__file__).resolve().parents[1]


class ProviderError(RuntimeError):
    """Raised when an external travel or carbon provider cannot answer safely."""


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def inverse_minmax(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 1.0
    return clamp(1.0 - ((value - minimum) / (maximum - minimum)))


def sustainability_weights(level: str) -> Dict[str, float]:
    level = (level or "balanced").lower()
    if level == "maximum":
        return {"carbon": 0.65, "price": 0.15, "preference": 0.20}
    if level == "eco":
        return {"carbon": 0.55, "price": 0.25, "preference": 0.20}
    return {"carbon": 0.45, "price": 0.35, "preference": 0.20}


def _normalised_metric(value: Optional[float], values: Sequence[Optional[float]], inverse: bool = True) -> float:
    """Normalise observed values while assigning missing values a neutral score."""
    observed = [float(v) for v in values if v is not None]
    if value is None or not observed:
        return 0.5
    minimum, maximum = min(observed), max(observed)
    if maximum <= minimum:
        return 1.0
    score = (float(value) - minimum) / (maximum - minimum)
    return 1.0 - score if inverse else score


def rank_options(options: List[Dict[str, Any]], sustainability_level: str = "balanced") -> List[Dict[str, Any]]:
    """Rank options using carbon impact, price, and explicit preference alignment.

    Carbon and price are normalised inside the returned option set, which prevents
    incompatible units from dominating the weighted score. Missing verified values
    receive a neutral component rather than an artificially favourable zero value.
    """
    if not options:
        return []
    carbons = [float(x["carbon_kg"]) if x.get("carbon_kg") is not None else None for x in options]
    prices = [float(x["price"]) if x.get("price") is not None else None for x in options]
    weights = sustainability_weights(sustainability_level)
    ranked: List[Dict[str, Any]] = []
    for item in options:
        carbon = float(item["carbon_kg"]) if item.get("carbon_kg") is not None else None
        price = float(item["price"]) if item.get("price") is not None else None
        preference = float(item.get("preference_match", item.get("local_score", 0.75)) or 0.75)
        carbon_score = _normalised_metric(carbon, carbons, inverse=True)
        price_score = _normalised_metric(price, prices, inverse=True)
        score = (
            weights["carbon"] * carbon_score
            + weights["price"] * price_score
            + weights["preference"] * clamp(preference)
        )
        row = dict(item)
        row["eco_score"] = round(score * 100, 1)
        if carbon is None:
            row["emission_band"] = "amber"
        else:
            row["emission_band"] = "green" if carbon_score >= 0.67 else ("amber" if carbon_score >= 0.34 else "red")
        row["score_components"] = {
            "carbon": round(carbon_score, 3),
            "price": round(price_score, 3),
            "preference": round(clamp(preference), 3),
        }
        ranked.append(row)
    return sorted(ranked, key=lambda x: x["eco_score"], reverse=True)


class ClimatiqClient:
    """Distance-based travel carbon estimator using the current Climatiq endpoint."""

    BASE_URL = "https://api.climatiq.io/travel/v1/distance"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 2.4):
        self.api_key = api_key or os.getenv("CLIMATIQ_API_KEY")
        self.timeout = timeout

    def estimate_distance_travel(self, origin: str, destination: str, mode: str) -> Dict[str, Any]:
        if not self.api_key:
            raise ProviderError("CLIMATIQ_API_KEY is not configured")
        mode_map = {"plane": "air", "flight": "air", "train": "rail", "rail": "rail", "car": "car", "air": "air"}
        travel_mode = mode_map.get((mode or "rail").lower(), (mode or "rail").lower())
        if travel_mode not in {"air", "car", "rail"}:
            raise ProviderError("Climatiq travel mode must be air, car, or rail")
        payload = {"origin": {"query": origin}, "destination": {"query": destination}, "travel_mode": travel_mode}
        try:
            response = requests.post(
                self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                raise ProviderError(f"Climatiq HTTP {response.status_code}: {response.text[:180]}")
            data = response.json()
            return {
                "co2e": float(data["co2e"]),
                "unit": data.get("co2e_unit", "kg"),
                "distance_km": data.get("distance_km"),
                "source": "climatiq",
                "raw": data,
            }
        except (requests.RequestException, KeyError, ValueError) as exc:
            raise ProviderError(f"Climatiq request failed: {exc}") from exc


class OpenRouteServiceClient:
    """Optional low-carbon local routing adapter for coordinate-based journeys."""

    BASE_URL = "https://api.openrouteservice.org/v2/directions"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 2.4):
        self.api_key = api_key or os.getenv("OPENROUTESERVICE_API_KEY")
        self.timeout = timeout

    def route(self, start_lonlat: Sequence[float], end_lonlat: Sequence[float], profile: str = "foot-walking") -> Dict[str, Any]:
        if not self.api_key:
            raise ProviderError("OPENROUTESERVICE_API_KEY is not configured")
        allowed = {"foot-walking", "cycling-regular", "driving-car"}
        if profile not in allowed:
            raise ProviderError(f"Unsupported OpenRouteService profile: {profile}")
        try:
            response = requests.post(
                f"{self.BASE_URL}/{profile}",
                headers={"Authorization": self.api_key, "Content-Type": "application/json"},
                json={"coordinates": [list(start_lonlat), list(end_lonlat)]},
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                raise ProviderError(f"OpenRouteService HTTP {response.status_code}: {response.text[:180]}")
            data = response.json()
            summary = data["features"][0]["properties"]["summary"]
            return {
                "distance_km": round(float(summary["distance"]) / 1000.0, 2),
                "duration_min": round(float(summary["duration"]) / 60.0, 1),
                "profile": profile,
                "source": "openrouteservice",
            }
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"OpenRouteService request failed: {exc}") from exc


class AmadeusLegacyClient:
    """Compatibility adapter for the assignment brief's former Self-Service API.

    No default base URL is enabled. An authorised enterprise-compatible endpoint
    can be supplied explicitly through environment configuration for assessor use.
    """

    def __init__(self):
        self.client_id = os.getenv("AMADEUS_CLIENT_ID")
        self.client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
        self.base_url = os.getenv("AMADEUS_BASE_URL", "").rstrip("/")
        self.timeout = float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "2.4"))
        self._token: Optional[str] = None
        self._token_expiry = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret and self.base_url)

    def _access_token(self) -> str:
        if not self.enabled:
            raise ProviderError("Amadeus adapter is disabled; configure authorised credentials and AMADEUS_BASE_URL")
        if self._token and time.time() < self._token_expiry - 30:
            return self._token
        response = requests.post(
            f"{self.base_url}/v1/security/oauth2/token",
            data={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Amadeus token HTTP {response.status_code}: {response.text[:180]}")
        data = response.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + int(data.get("expires_in", 1800))
        return self._token

    def search_flights(self, origin_code: str, destination_code: str, departure_date: str, adults: int = 1) -> List[Dict[str, Any]]:
        token = self._access_token()
        response = requests.get(
            f"{self.base_url}/v2/shopping/flight-offers",
            params={
                "originLocationCode": origin_code,
                "destinationLocationCode": destination_code,
                "departureDate": departure_date,
                "adults": adults,
                "max": 5,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Amadeus flight HTTP {response.status_code}: {response.text[:180]}")
        return response.json().get("data", [])

    def search_hotels_by_city(self, city_code: str) -> List[Dict[str, Any]]:
        token = self._access_token()
        response = requests.get(
            f"{self.base_url}/v1/reference-data/locations/hotels/by-city",
            params={"cityCode": city_code},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Amadeus hotel HTTP {response.status_code}: {response.text[:180]}")
        return response.json().get("data", [])[:8]


class DemoTravelProvider:
    """Clearly labelled deterministic provider used when live inventory is unavailable."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or ROOT / "mock_data" / "travel_options.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def options(self, destination: str) -> Dict[str, List[Dict[str, Any]]]:
        destination_key = (destination or "").lower()
        hotels = [x for x in self.data["hotels"] if not destination_key or x.get("city", "").lower() == destination_key]
        if not hotels:
            hotels = self.data["hotels"][:2]
        activities = [x for x in self.data["activities"] if not destination_key or x.get("city", "").lower() == destination_key]
        return {"hotels": hotels, "transport": self.data["flights"], "activities": activities or self.data["activities"]}


CITY_IATA = {
    "amsterdam": "AMS",
    "berlin": "BER",
    "copenhagen": "CPH",
    "paris": "PAR",
    "vienna": "VIE",
    "zurich": "ZRH",
    "stockholm": "STO",
    "lisbon": "LIS",
    "barcelona": "BCN",
    "prague": "PRG",
    "oslo": "OSL",
    "munich": "MUC",
}


def city_iata(city: str) -> Optional[str]:
    value = (city or "").strip()
    if len(value) == 3 and value.isalpha():
        return value.upper()
    return CITY_IATA.get(value.lower())


def normalise_amadeus_flights(records: List[Dict[str, Any]], carbon_kg: Optional[float]) -> List[Dict[str, Any]]:
    """Convert common Flight Offers response fields into frontend card records."""
    result: List[Dict[str, Any]] = []
    for index, record in enumerate(records[:5], start=1):
        price = record.get("price", {})
        itinerary = (record.get("itineraries") or [{}])[0]
        segments = itinerary.get("segments") or []
        carriers = [segment.get("carrierCode") for segment in segments if segment.get("carrierCode")]
        result.append(
            {
                "name": f"Flight option {index}" + (f" ({'/'.join(carriers)})" if carriers else ""),
                "carbon_kg": carbon_kg,
                "price": float(price.get("grandTotal")) if price.get("grandTotal") else None,
                "currency": price.get("currency", ""),
                "preference_match": 0.55,
                "verification_status": "live_inventory_not_environmentally_certified",
            }
        )
    return result


def normalise_amadeus_hotels(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Expose live hotel inventory without making unsupported sustainability claims."""
    result: List[Dict[str, Any]] = []
    for index, record in enumerate(records[:8], start=1):
        result.append(
            {
                "name": record.get("name") or f"Hotel option {index}",
                "hotel_id": record.get("hotelId"),
                "price": None,
                "carbon_kg": None,
                "currency": "",
                "preference_match": 0.5,
                "verification_status": "inventory_only_environmental_claim_unverified",
            }
        )
    return result


def build_handover_context(sender_id: str, slots: Dict[str, Any], latest_text: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    recent: List[Dict[str, str]] = []
    for event in events[-30:]:
        if event.get("event") in {"user", "bot"}:
            recent.append({"event": event.get("event"), "text": (event.get("text", "") or "")[:500]})
    permitted_slots = {
        key: value
        for key, value in slots.items()
        if key in {
            "origin",
            "destination",
            "start_date",
            "end_date",
            "budget",
            "sustainability_level",
            "travel_mode",
            "origin_lat",
            "origin_lon",
            "location_consent",
        }
        and value is not None
    }
    return {
        "sender_id": sender_id,
        "slots": permitted_slots,
        "latest_user_text": latest_text,
        "recent_turns": recent,
        "privacy_notice": "Context contains only conversation data needed for advisor continuity.",
        "status": "queued",
    }
