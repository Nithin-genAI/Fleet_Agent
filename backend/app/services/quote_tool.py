"""
Real scraping for fleet quotes. Two categories of fleet:

  - "standard"  : long-haul, pincode-to-pincode business shipping
                  (WareIQ, NimbusPost, Delhivery, Shiprocket — multi-courier aggregators)
  - "quick"     : intra-city same-day quick-commerce for D2C/B2C
                  (Borzo, Porter — city/address based)

Every quote dict carries a `category` so the agent and dashboard can tell
the two lanes apart and pick on speed vs. cost accordingly.

Same fallback pattern we use everywhere: try the real scrape, catch ANY
failure, fall back to mock so a live demo never dies on a broken selector
or a slow page load.

ARCHITECTURE UPDATES:
  - Parallel fetching: all scrapers run concurrently via ThreadPoolExecutor,
    so total quote time = max(scraper) instead of sum(scraper). A 45s
    timeout per scraper × 4 scrapers = 45s wall time, not 180s.
  - Circuit breaker: after 3 consecutive failures, a scraper is skipped for
    5 minutes to avoid wasting time on a dead site. Resets automatically.
  - Delhivery & Shiprocket: attempted but documented as unreliable (login-gated /
    test-pincode-rejecting). They return [] gracefully and the mock fallback
    tops up the list.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

PAGE_TIMEOUT_MS = 12000  # 12s per scraper — parallel fetch means total wall time is ~12s max, not 12s × N
SCRAPER_GOTO_TIMEOUT_MS = 10000  # page.goto timeout — if the page itself doesn't load in 10s, bail
SCRAPER_RESULT_TIMEOUT_MS = 8000  # wait_for_selector for result elements — if results don't appear in 8s, bail

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


# ---------------------------------------------------------------------------
# Circuit breaker — skip a scraper after N consecutive failures for a cooldown
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Per-scraper circuit breaker. After `failure_threshold` consecutive
    failures, the circuit opens and is_open() returns True for `reset_timeout`
    seconds. After that, it half-opens (allows one attempt)."""

    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failures: dict[str, int] = {}
        self._last_fail: dict[str, float] = {}

    def is_open(self, name: str) -> bool:
        if self._failures.get(name, 0) < self.failure_threshold:
            return False
        # Check if cooldown has elapsed → half-open
        if time.time() - self._last_fail.get(name, 0) > self.reset_timeout:
            self._failures[name] = 0
            return False
        return True

    def record_failure(self, name: str):
        self._failures[name] = self._failures.get(name, 0) + 1
        self._last_fail[name] = time.time()

    def record_success(self, name: str):
        self._failures[name] = 0


_breaker = CircuitBreaker()


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
    if _breaker.is_open("wareiq"):
        return []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://wareiq.com/wareiq-shipping-calculator/", timeout=SCRAPER_GOTO_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)  # SPA needs a moment to render the form

            page.locator("#pickup-pincode").fill(origin)
            page.locator("#delivery-pincode").fill(destination)
            page.locator("#weight").fill(str(weight_kg))
            page.locator("input[name='payment_mode']").first.check()  # Prepaid
            page.locator("#shipment-value").fill(DEFAULT_SHIPMENT_VALUE)

            page.locator("button.shipcalc__trigger-btn").click()  # the "Calculate" button
            page.wait_for_selector("#shipcalc__table-body tr", timeout=SCRAPER_RESULT_TIMEOUT_MS)
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
            if results:
                _breaker.record_success("wareiq")
            return results
    except Exception:
        _breaker.record_failure("wareiq")
        return []


def get_nimbuspost_quotes(origin: str, destination: str, weight_kg: float) -> list[dict]:
    """nimbuspost.com multi-courier calculator. Verified selectors. Returns [] on any failure."""
    if _breaker.is_open("nimbuspost"):
        return []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://nimbuspost.com/shipping-rate-calculator/", timeout=SCRAPER_GOTO_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            page.locator("input[name='pickup_pincode']").fill(origin)
            page.locator("input[name='delivery_pincode']").fill(destination)
            page.locator("input[name='weight']").fill(str(weight_kg))
            page.locator("#option1").check()  # Prepaid
            page.locator("#shipmentValue").fill(DEFAULT_SHIPMENT_VALUE)

            page.locator("#calculate-btn").click()
            # Results render into a table inside the result box.
            page.wait_for_selector("#shipping-calc-result_new table tbody tr", timeout=SCRAPER_RESULT_TIMEOUT_MS)
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
            if results:
                _breaker.record_success("nimbuspost")
            return results
    except Exception:
        _breaker.record_failure("nimbuspost")
        return []


def get_delhivery_quotes(origin: str, destination: str, weight_kg: float) -> list[dict]:
    """delhivery.com calculator. Often rejects test pincodes or requires COD/Prepaid
    toggle. Attempted with best-known selectors; returns [] on any failure.
    Documented gap — not a silent one."""
    if _breaker.is_open("delhivery"):
        return []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.delhivery.com/calculator/", timeout=SCRAPER_GOTO_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Delhivery's form fields — these may shift; the try/except catches that.
            page.locator("input[name='pickup_pincode'], #pickup_pincode").first.fill(origin)
            page.locator("input[name='destination_pincode'], #destination_pincode").first.fill(destination)
            page.locator("input[name='weight'], #weight").first.fill(str(weight_kg))
            page.locator("input[name='cod'], #cod").first.check()  # Prepaid (toggle)
            page.locator("input[name='declared_value'], #declared_value").first.fill(DEFAULT_SHIPMENT_VALUE)

            # Try multiple button selectors
            calc_btn = page.locator("button:has-text('Calculate'), button:has-text('Get Quote'), #calculate-btn").first
            calc_btn.click()
            page.wait_for_timeout(3000)

            # Results may appear in a table or a div — try both
            results = []
            rows = page.locator("table tbody tr, .result-row, .quote-row").all()
            for row in rows:
                cells = row.locator("td, .price, .rate").all()
                if len(cells) < 2:
                    continue
                name_text = cells[0].inner_text().strip()
                price_text = cells[-1].inner_text().strip() if cells else ""
                if name_text and price_text:
                    results.append({
                        "fleet_name": name_text,
                        "price": _price_from_text(price_text),
                        "eta_hours": _parse_edd_hours(cells[1].inner_text()) if len(cells) > 1 else None,
                        "source": "delhivery_live",
                        "category": "standard",
                    })

            browser.close()
            if results:
                _breaker.record_success("delhivery")
            return results
    except Exception:
        _breaker.record_failure("delhivery")
        return []


def get_shiprocket_quotes(origin: str, destination: str, weight_kg: float) -> list[dict]:
    """shiprocket.in shipping-rate-calculator. Login-gated in practice — the
    public calculator redirects to a sign-up form. Attempted anyway; returns []
    on failure. Documented gap — not a silent one."""
    if _breaker.is_open("shiprocket"):
        return []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.shiprocket.in/shipping-rate-calculator/", timeout=SCRAPER_GOTO_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # If redirected to login, the form fields won't exist → returns []
            pincode_input = page.locator("input[placeholder*='pincode'], input[name='pickup_pincode']").first
            if not pincode_input.is_visible():
                browser.close()
                return []

            pincode_input.fill(origin)
            page.locator("input[placeholder*='delivery'], input[name='delivery_pincode']").first.fill(destination)
            page.locator("input[name='weight'], input[type='number']").first.fill(str(weight_kg))

            calc_btn = page.locator("button:has-text('Calculate'), button:has-text('Check'), button[type='submit']").first
            calc_btn.click()
            page.wait_for_timeout(3000)

            results = []
            rows = page.locator("table tbody tr, .courier-list .courier-item").all()
            for row in rows:
                cells = row.locator("td, .courier-name, .rate").all()
                if len(cells) < 2:
                    continue
                name_text = cells[0].inner_text().strip()
                price_text = cells[-1].inner_text().strip()
                if name_text and price_text:
                    results.append({
                        "fleet_name": name_text,
                        "price": _price_from_text(price_text),
                        "eta_hours": _parse_edd_hours(cells[1].inner_text()) if len(cells) > 1 else None,
                        "source": "shiprocket_live",
                        "category": "standard",
                    })

            browser.close()
            if results:
                _breaker.record_success("shiprocket")
            return results
    except Exception:
        _breaker.record_failure("shiprocket")
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
    if _breaker.is_open("borzo"):
        return None
    city = (quick.get("pickup_city") or "").strip()
    borzo_city = BORZO_CITY_MAP.get(city.lower())
    if not borzo_city:
        return None  # Borzo doesn't serve this city -> caller falls back to mock
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://borzodelivery.com/in/tariffs", timeout=SCRAPER_GOTO_TIMEOUT_MS, wait_until="domcontentloaded")
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
                _breaker.record_failure("borzo")
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

            _breaker.record_success("borzo")
            return {
                "fleet_name": f"Borzo ({borzo_city})",
                "price": price,
                "eta_hours": 4,  # same-day intra-city
                "source": "borzo_live",
                "category": "quick",
            }
    except Exception:
        _breaker.record_failure("borzo")
        return None


def get_porter_quote(city: str, weight_kg: float) -> dict | None:
    """
    Porter's old rate-calculator is gone (redirects to an OTP-gated lead form
    with no price output). Instead we scrape the per-city 2-wheeler landing
    page, which publishes a hardcoded base fare: "2 Wheeler, 20 kg, Starting
    From ₹48". This is a *base fare* (1 km included), not a route quote — the
    agent_reasoning labels it as such. Returns None on any failure.
    """
    if _breaker.is_open("porter"):
        return None
    slug = PORTER_CITY_SLUG.get((city or "").strip().lower())
    if not slug:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"https://porter.in/two-wheelers/{slug}", timeout=SCRAPER_GOTO_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            text = page.inner_text("body")
            browser.close()

            m = re.search(r"Starting\s*From\s*₹\s*([\d,]+)", text, re.I)
            if not m:
                _breaker.record_failure("porter")
                return None
            price = float(m.group(1).replace(",", ""))

            _breaker.record_success("porter")
            return {
                "fleet_name": f"Porter ({city.strip().title()})",
                "price": price,
                "eta_hours": 6,  # 2-wheeler intra-city
                "source": "porter_live",
                "category": "quick",
            }
    except Exception:
        _breaker.record_failure("porter")
        return None


# ---------------------------------------------------------------------------
# Aggregation — parallel fetching with ThreadPoolExecutor
# ---------------------------------------------------------------------------

def get_all_quotes(origin: str, destination: str, weight_kg: float, *, quick: dict | None = None) -> list[dict]:
    """
    Entry point the rest of the app calls. Runs all scrapers in PARALLEL via
    ThreadPoolExecutor, so total wait = max(scraper) not sum(scraper). Fills
    in with mock data for anything that failed, so the order flow never sees
    an empty quote list.

    Long-haul (standard) quotes are always fetched from pincodes. Quick-commerce
    quotes are only fetched when `quick` is provided with a pickup_city (the
    user filled the Quick Fleets section of the form).
    """
    live: list[dict] = []

    # Build the task list: (function, args, is_single_quote)
    tasks = [
        (get_wareiq_quotes, (origin, destination, weight_kg), False),
        (get_nimbuspost_quotes, (origin, destination, weight_kg), False),
        (get_delhivery_quotes, (origin, destination, weight_kg), False),
        (get_shiprocket_quotes, (origin, destination, weight_kg), False),
    ]

    if quick and (quick.get("pickup_city") or "").strip():
        tasks.append((get_borzo_quote, (quick, weight_kg), True))
        tasks.append((get_porter_quote, (quick["pickup_city"], weight_kg), True))

    # Run all scrapers in parallel — each Playwright instance runs in its own thread
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {
            executor.submit(fn, *args): (fn, is_single)
            for fn, args, is_single in tasks
        }
        for future in as_completed(future_map):
            fn, is_single = future_map[future]
            try:
                result = future.result()
                if result:
                    if is_single:
                        live.append(result)
                    else:
                        live.extend(result)
            except Exception:
                pass  # individual scraper failure — mock fallback tops up

    # Fallback / top-up with mock fleets for any name not already live
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
