"""
This is the tool the agent calls to get fleet options.

Build order matters here: we're shipping with MOCK data first so the
*entire* pipeline (quote -> select -> pay -> deliver/RTO -> reroute) can be
tested end-to-end today, before a single line of Playwright exists. This is
the actual professional way to work under a deadline: get the full loop
running on fake data, THEN replace one real component at a time. If you
build the scraper first in isolation, you won't know it's wired correctly
until everything else also exists — you'll debug two things at once under
time pressure.

Each get_*_quotes function returns the SAME shape regardless of source, so
swapping mock -> real is a one-line change in get_all_quotes().
"""
import random


def get_mock_quotes(origin: str, destination: str, weight_kg: float) -> list[dict]:
    """Deterministic-ish mock data, scaled by weight so it looks plausible in a demo."""
    base = 80 + weight_kg * 25
    return [
        {"fleet_name": "Porter", "price": round(base * 1.0, 2), "eta_hours": 6, "source": "mock"},
        {"fleet_name": "Shadowfax", "price": round(base * 0.85, 2), "eta_hours": 10, "source": "mock"},
        {"fleet_name": "DTDC", "price": round(base * 1.15, 2), "eta_hours": 18, "source": "mock"},
    ]


def get_porter_quote(origin: str, destination: str, weight_kg: float) -> dict | None:
    """
    TODO (real): Playwright against porter.in/courier/shipping-rate-calculator
    Fill pincode fields + weight, submit, extract displayed price.
    Return None on any scrape failure — caller falls back to mock for that fleet only.
    """
    raise NotImplementedError("Wire Playwright here")


def get_wareiq_quotes(origin: str, destination: str, weight_kg: float) -> list[dict]:
    """
    TODO (real): Playwright against WareIQ's multi-courier calculator.
    Returns a LIST because one page can yield several fleets (Shadowfax, DTDC, ...).
    Return [] on failure — caller falls back to mock for those fleets.
    """
    raise NotImplementedError("Wire Playwright here")


def get_all_quotes(origin: str, destination: str, weight_kg: float) -> list[dict]:
    """
    The single entry point the rest of the app calls. Swapping mock for real:
    wrap each real call in try/except, fall back to the matching mock entries
    on failure so a live scrape breaking never kills the demo.
    """
    return get_mock_quotes(origin, destination, weight_kg)
