"""
Real scraping for fleet quotes. Two categories of fleet:

  - "standard"  : long-haul, pincode-to-pincode business shipping
                  (WareIQ, NimbusPost — multi-courier aggregators)
  - "quick"     : intra-city same-day quick-commerce for D2C/B2C
                  (Borzo, Porter — city/address based)

Every quote dict carries a `category` so the agent and dashboard can tell
the two lanes apart and pick on speed vs. cost accordingly.

Same fallback pattern we use everywhere: try the real scrape, catch ANY
failure, fall back to mock so a live demo never dies on a broken selector
or a slow page load.

All selectors below were VERIFIED against the live DOM on 2026-09-08 by
loading each page in headless Chromium and dumping the real fields/result
markup — they are not guesses. If a site redesigns and one breaks, the
except-clause returns None/[] and mock data tops the list up.
"""
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

PAGE_TIMEOUT_MS = 45000

# These calculators mark Shipment Value as a required field, but the quote
# functions don't receive a package value, so we default to a modest prepaid
# shipment. (The selection agent DOES get package_value separately.)
DEFAULT_SHIPMENT_VALUE = "500"


# Borzo's city picker is a fixed list of buttons. Map the free-text city the
# user types (and common spellings) to the exact button label Borzo expects.
BORZO_CITY_MAP = {
    "mumbai": "Mumbai",
    "bengaluru": "Bengaluru", "bangalore": "Bengaluru",
    "delhi": "Delhi/NCR", "delhi/ncr": "Delhi/NCR", "new delhi": "Delhi/NCR",
    "pune": "Pune", "chennai": "Chennai", "hyderabad": "Hyderabad",
    "ahmedabad": "Ahmedabad", "kolkata": "Kolkata", "surat": "Surat",
    "vadodara": "Vadodara", "jaipur": "Jaipur", "goa": "Goa",
    "kanpur": "Kanpur", "indore": "Indore", "bhopal": "Bhopal",
    "chandigarh": "Chandigarh", "amritsar": "Amritsar",
    "guwahati": "Guwahati", "jodhpur": "Jodhpur", "kota": "Kota",
    "lucknow": "Lucknow", "udaipur": "Udaipur", "uttarakhand": "Uttarakhand",
}

# Porter publishes a per-city 2-wheeler landing page at porter.in/two-wheelers/<slug>.
PORTER_CITY_SLUG = {
    "bangalore": "bangalore", "bengaluru": "bangalore",
    "mumbai": "mumbai", "delhi": "delhi", "pune": "pune",
    "chennai": "chennai", "hyderabad": "hyderabad", "kolkata": "kolkata",
    "ahmedabad": "ahmedabad", "jaipur": "jaipur", "gurgaon": "gurgaon",
    "noida": "noida", "faridabad": "faridabad", "ghaziabad": "ghaziabad",
}


def _parse_edd_hours(text: str) -> int | None:
    """'4 Days' / '1 Day' / '6 days' -> hours; anything unparsable -> None."""
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) * 24 if m else None


def _price_from_text(text: str) -> float:
    """'₹ 123' / '₹1,234.50' -> 123.0 / 1234.5."""
    digits = "".join(c for c in text if c.isdigit() or c == ".")
    return float(digits) if digits else 0.0


def get_mock_quotes(origin: str, destination: str, weight_kg: float) -> list[dict]:
    """Fallback data, scaled by weight so it looks plausible in a demo.
    Porter is a quick-commerce fleet; the other two are long-haul."""
    base = 80 + weight_kg * 25
    return [
        {"fleet_name": "Porter", "price": round(base * 1.0, 2), "eta_hours": 6, "source": "mock", "category": "quick"},
        {"fleet_name": "Shadowfax", "price": round(base * 0.85, 2), "eta_hours": 10, "source": "mock", "category": "standard"},
        {"fleet_name": "DTDC", "price": round(base * 1.15, 2), "eta_hours": 18, "source": "mock", "category": "standard"},
    ]


# ---------------------------------------------------------------------------
# Long-haul (standard) scrapers — pincode to pincode
# ---------------------------------------------------------------------------

def get_wareiq_quotes(origin: str, destination: str, weight_kg: float) -> list[dict]:
    """wareiq.com multi-courier calculator. Verified selectors. Returns [] on any failure."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://wareiq.com/wareiq-shipping-calculator/", timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)  # SPA needs a moment to render the form

            page.locator("#pickup-pincode").fill(origin)
            page.locator("#delivery-pincode").fill(destination)
            page.locator("#weight").fill(str(weight_kg))
            page.locator("input[name='payment_mode']").first.check()  # Prepaid
            page.locator("#shipment-value").fill(DEFAULT_SHIPMENT_VALUE)

            page.locator("button.shipcalc__trigger-btn").click()  # the "Calculate" button
            page.wait_for_selector("#shipcalc__table-body tr", timeout=PAGE_TIMEOUT_MS)
            page.wait_for_timeout(1000)  # let all rows stream in

            results = []
            for row in page.locator("#shipcalc__table-body tr").all():
                cells = row.locator("td").all()
                if len(cells) < 4:
                    continue
                results.append({
                    "fleet_name": cells[1].inner_text().strip(),
                    "price": _price_from_text(cells[2].inner_text()),
                    "eta_hours": _parse_edd_hours(cells[3].inner_text()),
                    "source": "wareiq_live",
                    "category": "standard",
                })

            browser.close()
            return results
    except Exception:
        return []


def get_nimbuspost_quotes(origin: str, destination: str, weight_kg: float) -> list[dict]:
    """nimbuspost.com multi-courier calculator. Verified selectors. Returns [] on any failure."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://nimbuspost.com/shipping-rate-calculator/", timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            page.locator("input[name='pickup_pincode']").fill(origin)
            page.locator("input[name='delivery_pincode']").fill(destination)
            page.locator("input[name='weight']").fill(str(weight_kg))
            page.locator("#option1").check()  # Prepaid
            page.locator("#shipmentValue").fill(DEFAULT_SHIPMENT_VALUE)

            page.locator("#calculate-btn").click()
            # Results render into a table inside the result box.
            page.wait_for_selector("#shipping-calc-result_new table tbody tr", timeout=PAGE_TIMEOUT_MS)
            page.wait_for_timeout(1500)

            results = []
            for row in page.locator("#shipping-calc-result_new table tbody tr").all():
                cells = row.locator("td").all()
                if len(cells) < 4:
                    continue
                results.append({
                    "fleet_name": cells[0].inner_text().strip(),
                    "price": _price_from_text(cells[2].inner_text()),
                    "eta_hours": _parse_edd_hours(cells[3].inner_text()),
                    "source": "nimbuspost_live",
                    "category": "standard",
                })

            browser.close()
            return results
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Quick-commerce (quick) scrapers — intra-city, same-day
# ---------------------------------------------------------------------------

def get_borzo_quote(quick: dict, weight_kg: float) -> dict | None:
    """
    borzodelivery.com/in/tariffs — Borzo's (WeFast) intra-city 2-wheeler tariff.
    The page renders a per-city weight-bucket matrix (<=1/5/10/15/20 kg) as text.
    `quick` must contain pickup_city (and optionally pickup_area/drop_area).
    Returns a single quick-commerce quote, or None if the city isn't on Borzo's list.
    """
    city = (quick.get("pickup_city") or "").strip()
    borzo_city = BORZO_CITY_MAP.get(city.lower())
    if not borzo_city:
        return None  # Borzo doesn't serve this city -> caller falls back to mock
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://borzodelivery.com/in/tariffs", timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            # Select city, vehicle (2-Wheeler), account type (Individual) — defaults
            # are already 2-Wheeler/Individual, but be explicit.
            page.get_by_role("button", name=borzo_city, exact=True).click()
            page.wait_for_timeout(2500)

            text = page.inner_text("body")
            browser.close()

            # The matrix reads: "up to 1 kg up to 5 kg ... up to 20 kg ₹32 ₹32 ₹122 ₹167 ₹212 Per additional km ..."
            # Grab the price run between the bucket headers and "Per additional".
            m = re.search(r"up to 1\s*kg.*?(₹.*?)(?:Per additional|Calculate the price)", text, re.I | re.S)
            segment = m.group(1) if m else text
            prices = re.findall(r"₹\s*([\d,.]+)", segment)
            if len(prices) < 5:
                return None
            buckets = [float(pr.replace(",", "")) for pr in prices[:5]]  # <=1,<=5,<=10,<=15,<=20 kg

            if weight_kg <= 1:
                price = buckets[0]
            elif weight_kg <= 5:
                price = buckets[1]
            elif weight_kg <= 10:
                price = buckets[2]
            elif weight_kg <= 15:
                price = buckets[3]
            elif weight_kg <= 20:
                price = buckets[4]
            else:
                return None  # 2-wheeler caps at 20 kg

            return {
                "fleet_name": f"Borzo ({borzo_city})",
                "price": price,
                "eta_hours": 4,  # same-day intra-city
                "source": "borzo_live",
                "category": "quick",
            }
    except Exception:
        return None


def get_porter_quote(city: str, weight_kg: float) -> dict | None:
    """
    Porter's old rate-calculator is gone (redirects to an OTP-gated lead form
    with no price output). Instead we scrape the per-city 2-wheeler landing
    page, which publishes a hardcoded base fare: "2 Wheeler, 20 kg, Starting
    From ₹48". This is a *base fare* (1 km included), not a route quote — the
    agent_reasoning labels it as such. Returns None on any failure.
    """
    slug = PORTER_CITY_SLUG.get((city or "").strip().lower())
    if not slug:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"https://porter.in/two-wheelers/{slug}", timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            text = page.inner_text("body")
            browser.close()

            m = re.search(r"Starting\s*From\s*₹\s*([\d,]+)", text, re.I)
            if not m:
                return None
            price = float(m.group(1).replace(",", ""))

            return {
                "fleet_name": f"Porter ({city.strip().title()})",
                "price": price,
                "eta_hours": 6,  # 2-wheeler intra-city
                "source": "porter_live",
                "category": "quick",
            }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def get_all_quotes(origin: str, destination: str, weight_kg: float, *, quick: dict | None = None) -> list[dict]:
    """
    Entry point the rest of the app calls. Tries real sources first, fills in
    with mock data for anything that failed, so the order flow never sees an
    empty quote list.

    Long-haul (standard) quotes are always fetched from pincodes. Quick-commerce
    quotes are only fetched when `quick` is provided with a pickup_city (the
    user filled the Quick Fleets section of the form).
    """
    live: list[dict] = []

    # 1. long-haul aggregators (pincode -> pincode)
    live.extend(get_wareiq_quotes(origin, destination, weight_kg))
    live.extend(get_nimbuspost_quotes(origin, destination, weight_kg))

    # 2. quick-commerce (intra-city), only if the user provided a city
    if quick and (quick.get("pickup_city") or "").strip():
        borzo = get_borzo_quote(quick, weight_kg)
        if borzo:
            live.append(borzo)
        porter = get_porter_quote(quick["pickup_city"], weight_kg)
        if porter:
            live.append(porter)

    # 3. fallback / top-up with mock fleets for any name not already live
    if not live:
        return get_mock_quotes(origin, destination, weight_kg)

    have = {q["fleet_name"] for q in live}
    for mock_q in get_mock_quotes(origin, destination, weight_kg):
        if mock_q["fleet_name"] not in have:
            live.append(mock_q)

    return live


if __name__ == "__main__":
    # Quick manual check: `python -m app.services.quote_tool` from backend/
    # Long-haul only:
    print("=== long-haul (pincode only) ===")
    for q in get_all_quotes("560001", "400001", 2):
        print(q)
    # Long-haul + quick-commerce (user filled Quick Fleets):
    print("\n=== with quick fleets (Bengaluru) ===")
    for q in get_all_quotes("560001", "400001", 2, quick={
        "pickup_area": "Koramangala", "pickup_city": "Bengaluru",
        "drop_area": "Indiranagar", "drop_city": "Bengaluru",
    }):
        print(q)
