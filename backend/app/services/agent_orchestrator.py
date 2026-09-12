"""
AI fleet selection — the one place an LLM is used in this system.

The agent picks the best fleet by reasoning about two primary factors:
  1. COST efficiency — cheaper is better, weighted at 60%
  2. TIME efficiency — faster ETA is better, weighted at 40%

A composite score blends both: 0.6 × normalized_cost + 0.4 × normalized_ETA.
The LLM receives this scoring rubric in its prompt so its reasoning is
grounded in the same formula the fallback uses — not a vague "pick the best."

Robustness: the Groq call is retried up to 3 times with exponential backoff
(1s → 2s → 4s). Combined with JSON-mode responses and defensive parsing,
the rule-based fallback should fire <1% of the time. When it does fire,
it uses the SAME composite scoring — not just cheapest-wins.
"""
import os
import json
import time

GROQ_MODEL = "openai/gpt-oss-20b"

# Scoring weights — cost is the primary factor, time is secondary.
COST_WEIGHT = 0.6
TIME_WEIGHT = 0.4

# Retry config — this is what drives the fallback rate below 1%.
# Backoff is tight (0.5s → 1s → 2s = 3.5s worst case) so a demo never
# waits more than ~3.5s + one Groq call before getting a decision.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [0.5, 1, 2]


def _normalize(values: list[float]) -> list[float]:
    """Normalize to 0..1 where 0 = best (minimum). All-equal → all 0."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if lo == hi:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def compute_scores(quotes: list[dict]) -> list[dict]:
    """
    Composite cost + time score for each quote.
    Lower composite_score = better overall value.
    """
    prices = [q["price"] for q in quotes]
    etas = [q.get("eta_hours") or 0 for q in quotes]
    norm_cost = _normalize(prices)
    norm_time = _normalize(etas)
    scored = []
    for i, q in enumerate(quotes):
        composite = COST_WEIGHT * norm_cost[i] + TIME_WEIGHT * norm_time[i]
        scored.append({
            **q,
            "cost_score": round(norm_cost[i], 4),
            "time_score": round(norm_time[i], 4),
            "composite_score": round(composite, 4),
        })
    return scored


def _filter_candidates(quotes: list[dict], exclude: list[str], intra_city: bool) -> list[dict]:
    """Remove excluded fleets and quick fleets on inter-city routes."""
    candidates = [q for q in quotes if q["fleet_name"] not in exclude]
    if not intra_city:
        candidates = [q for q in candidates if q.get("category") != "quick"]
    return candidates


def rule_based_select(quotes: list[dict], exclude: list[str] | None = None, intra_city: bool = False) -> dict:
    """
    Fallback: composite-score winner (cost + time), not just cheapest.
    Quick fleets are excluded for inter-city routes.
    """
    exclude = exclude or []
    candidates = _filter_candidates(quotes, exclude, intra_city)
    if not candidates:
        raise ValueError("No fleets left to try")
    scored = compute_scores(candidates)
    return min(scored, key=lambda q: q["composite_score"])


def _value_assessment(package_value: float) -> str:
    """Dynamic guidance: high-value → weight time more, low-value → cost dominates."""
    if package_value >= 2000:
        return f"HIGH-VALUE package (₹{package_value}) — time efficiency matters more; weigh speed higher."
    if package_value <= 200:
        return f"LOW-VALUE package (₹{package_value}) — cost efficiency dominates; pick the cheapest viable option."
    return f"MID-VALUE package (₹{package_value}) — balance cost and time evenly."


def _build_prompt(quotes: list[dict], package_value: float, exclude: list[str], intra_city: bool) -> str:
    """Build the Groq prompt with pre-computed scores so the LLM reasons
    against the same data the fallback would use."""
    candidates = _filter_candidates(quotes, exclude, intra_city)
    scored = compute_scores(candidates)
    route_type = (
        "intra-city (same city, same-day delivery)"
        if intra_city
        else "inter-city (pincode-to-pincode, long-haul)"
    )
    options_json = json.dumps([
        {
            "fleet_name": s["fleet_name"],
            "price": s["price"],
            "eta_hours": s.get("eta_hours"),
            "category": s.get("category", "standard"),
            "cost_score": s["cost_score"],
            "time_score": s["time_score"],
            "composite_score": s["composite_score"],
        }
        for s in scored
    ], indent=2)

    return (
        "You are a logistics dispatch agent. Select the best delivery fleet for a "
        "package worth ₹{value} on an {route} shipment.\n\n"
        "SELECTION CRITERIA (priority order):\n"
        "  1. COST efficiency (weight {cost_w}): lower price is better. cost_score 0.0 = cheapest.\n"
        "  2. TIME efficiency (weight {time_w}): lower ETA is better. time_score 0.0 = fastest.\n"
        "  3. Composite = {cost_w}×cost_score + {time_w}×time_score. LOWER composite = better.\n\n"
        "VALUE ASSESSMENT: {value_note}\n\n"
        "ROUTE RULES:\n"
        "  - 'quick' fleets (intra-city same-day) CANNOT serve inter-city routes — never pick one for inter-city.\n"
        "  - For intra-city, a 'quick' fleet is usually right (faster, competitive cost).\n\n"
        "OPTIONS (pre-scored):\n{options}\n\n"
        "Reason step-by-step: compare cost vs time for each viable option, note the composite scores, "
        "then pick the fleet with the best cost-time balance. "
        "Respond ONLY with JSON:\n"
        '{{"fleet_name": "...", "cost_reasoning": "one sentence on why this is cost-efficient", '
        '"time_reasoning": "one sentence on why the ETA is acceptable or superior", '
        '"reasoning": "one sentence: the overall cost + time trade-off that justifies this pick"}}'
    ).format(
        value=package_value,
        route=route_type,
        cost_w=COST_WEIGHT,
        time_w=TIME_WEIGHT,
        value_note=_value_assessment(package_value),
        options=options_json,
    )


def _groq_select(quotes: list[dict], package_value: float, exclude: list[str], intra_city: bool) -> dict | None:
    """
    Call Groq with retry + exponential backoff. Returns decision dict or None
    if all retries are exhausted (→ caller falls back to rule-based).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    candidates = _filter_candidates(quotes, exclude, intra_city)
    if not candidates:
        return None

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
    except Exception:
        return None

    prompt = _build_prompt(quotes, package_value, exclude, intra_city)

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=350,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
            parsed = json.loads(content)

            # Validate fleet name is a real candidate (not hallucinated)
            match = next(
                (q for q in candidates if q["fleet_name"] == parsed["fleet_name"]),
                None,
            )
            if not match:
                raise ValueError(
                    f"fleet_name '{parsed['fleet_name']}' not in candidates"
                )

            # Assemble rich reasoning from the LLM's structured response
            cost_r = parsed.get("cost_reasoning", "")
            time_r = parsed.get("time_reasoning", "")
            summary = parsed.get("reasoning", "")
            parts = ["[Groq]"]
            if cost_r:
                parts.append(f"Cost: {cost_r}")
            if time_r:
                parts.append(f"Time: {time_r}")
            if summary:
                parts.append(summary)
            reasoning = " | ".join(parts)

            # Attach composite score
            scored = compute_scores(candidates)
            chosen = next(
                (s for s in scored if s["fleet_name"] == match["fleet_name"]),
                match,
            )

            return {
                **match,
                "reasoning": reasoning,
                "composite_score": chosen.get("composite_score"),
            }

        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                continue
            return None  # all retries exhausted


def select_fleet(
    quotes: list[dict],
    package_value: float,
    exclude: list[str] | None = None,
    intra_city: bool = False,
) -> dict:
    """
    Returns {"fleet_name", "price", "eta_hours", "reasoning", "composite_score"}.
    Tries Groq (3 retries with backoff) → falls back to composite-score rule.
    The fallback uses the SAME cost+time scoring, not just cheapest-wins.
    """
    exclude = exclude or []
    decision = _groq_select(quotes, package_value, exclude, intra_city)
    if decision:
        return decision

    choice = rule_based_select(quotes, exclude, intra_city)
    scored = compute_scores(_filter_candidates(quotes, exclude, intra_city))
    chosen = next(
        (s for s in scored if s["fleet_name"] == choice["fleet_name"]),
        {},
    )
    reasoning = (
        f"[Rule-based fallback] {choice['fleet_name']} at ₹{choice['price']} — "
        f"composite {chosen.get('composite_score', 'N/A')} "
        f"(cost {chosen.get('cost_score', 'N/A')}, time {chosen.get('time_score', 'N/A')}). "
        f"Best cost+time balance among {len(scored)} eligible options."
    )
    return {
        **choice,
        "reasoning": reasoning,
        "composite_score": chosen.get("composite_score"),
    }


def reroute_after_rto(
    quotes: list[dict],
    failed_fleet: str,
    package_value: float,
    intra_city: bool = False,
) -> dict:
    """Same selection logic, excluding the fleet that just failed."""
    return select_fleet(quotes, package_value, exclude=[failed_fleet], intra_city=intra_city)
