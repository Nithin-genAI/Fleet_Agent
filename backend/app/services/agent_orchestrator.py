"""
AI fleet selection — the one place an LLM is used in this system.

The agent is STATELESS and AUTONOMOUS: it receives the full set of live quotes
and independently reasons about which fleet offers the best cost-time trade-off.
No pre-computed scores are injected — the LLM derives its own assessment from
the raw price and ETA data, which makes the selection genuinely agentic rather
than a rubber-stamp on a formula.

SELECTION CRITERIA the agent considers:
  1. COST efficiency — lower price is better (weighted ~60%)
  2. TIME efficiency — lower ETA is better (weighted ~40%)
  3. Category constraints — quick fleets can't serve inter-city routes

Robustness: the Groq call is retried up to 3 times with exponential backoff.
If all retries are exhausted (or no API key), a rule-based composite-score
fallback fires. The fallback uses the SAME cost+time logic — not just cheapest.
"""
import os
import json
import time
import re

GROQ_MODEL = "openai/gpt-oss-20b"

# Scoring weights — used by the rule-based fallback only. The LLM derives
# its own reasoning from the raw data, but when it fails we fall back to
# this formula so the fallback is still intelligent, not just cheapest-wins.
COST_WEIGHT = 0.6
TIME_WEIGHT = 0.4

# Retry config — backoff is tight (0.5s → 1s → 2s = 3.5s worst case).
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
    """Composite cost + time score for each quote. Lower = better."""
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
    """Fallback: composite-score winner (cost + time), not just cheapest."""
    exclude = exclude or []
    candidates = _filter_candidates(quotes, exclude, intra_city)
    if not candidates:
        raise ValueError("No fleets left to try")
    scored = compute_scores(candidates)
    return min(scored, key=lambda q: q["composite_score"])


def _value_assessment(package_value: float) -> str:
    """Dynamic guidance: high-value → weight time more, low-value → cost dominates."""
    if package_value >= 2000:
        return f"HIGH-VALUE package (Rs {package_value}) — time efficiency matters more; weigh speed higher."
    if package_value <= 200:
        return f"LOW-VALUE package (Rs {package_value}) — cost efficiency dominates; pick the cheapest viable option."
    return f"MID-VALUE package (Rs {package_value}) — balance cost and time evenly."


def _build_prompt(quotes: list[dict], package_value: float, exclude: list[str], intra_city: bool) -> str:
    """Build the Groq prompt with raw quote data — no pre-computed scores.
    The LLM derives its own cost-time assessment, making the selection genuinely
    autonomous rather than a rubber-stamp on a formula."""
    candidates = _filter_candidates(quotes, exclude, intra_city)
    route_type = (
        "intra-city (same city, same-day delivery)"
        if intra_city
        else "inter-city (pincode-to-pincode, long-haul)"
    )
    options_json = json.dumps([
        {
            "fleet_name": q["fleet_name"],
            "price": q["price"],
            "eta_hours": q.get("eta_hours"),
            "category": q.get("category", "standard"),
            "source": q.get("source", "unknown"),
        }
        for q in candidates
    ])

    return (
        f"Select the best delivery fleet for a {route_type} shipment worth Rs {package_value}.\n\n"
        f"SELECTION CRITERIA (priority order):\n"
        f"  1. COST efficiency (weight 0.6): lower price is better.\n"
        f"  2. TIME efficiency (weight 0.4): lower ETA is better.\n"
        f"  3. Composite = 0.6 x cost_score + 0.4 x time_score. LOWER = better.\n\n"
        f"VALUE ASSESSMENT: {_value_assessment(package_value)}\n\n"
        f"ROUTE RULES:\n"
        f"  - 'quick' fleets (intra-city same-day) CANNOT serve inter-city routes.\n"
        f"  - For intra-city, a 'quick' fleet is usually right (faster, competitive cost).\n"
        f"  - Always prefer a fleet that is BOTH cheaper AND faster when one exists.\n\n"
        f"OPTIONS (live quotes):\n{options_json}\n\n"
        f"Reason step-by-step: compare cost vs time for each viable option, "
        f"identify which fleet is both cheapest and fastest if one exists, "
        f"then pick the fleet with the best cost-time balance. "
        f"Respond ONLY with JSON:\n"
        f'{{"fleet_name": "exact fleet name from options", '
        f'"cost_reasoning": "one sentence on why this is cost-efficient", '
        f'"time_reasoning": "one sentence on why the ETA is acceptable or superior", '
        f'"reasoning": "one sentence: the overall cost + time trade-off that justifies this pick"}}'
    )


def _extract_json(content: str) -> dict | None:
    """Extract a JSON object from a text response, handling cases where the
    LLM wraps JSON in markdown code blocks or adds extra text."""
    # Try direct parse first
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting from markdown code block
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try extracting the first {...} block
    m = re.search(r'\{.*\}', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _groq_select(quotes: list[dict], package_value: float, exclude: list[str], intra_city: bool) -> dict | None:
    """
    Call Groq with retry + exponential backoff. Returns decision dict or None
    if all retries are exhausted (→ caller falls back to rule-based).

    Uses a two-phase approach:
      1. Try with JSON mode (structured output) first.
      2. If JSON mode fails, retry without JSON mode and extract JSON manually.
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
    system_msg = (
        "You are a logistics dispatch agent. You select the best delivery fleet "
        "by independently reasoning about cost and time efficiency. "
        "You always respond with valid JSON only."
    )

    for attempt in range(MAX_RETRIES):
        try:
            # Phase 1: Try with JSON mode (attempts 0 and 1)
            # Phase 2: Try without JSON mode and extract manually (attempt 2)
            if attempt < 2:
                resp = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=800,
                    response_format={"type": "json_object"},
                )
            else:
                # Last attempt: no JSON mode, extract manually
                resp = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=800,
                )

            content = resp.choices[0].message.content
            if not content or not content.strip():
                raise ValueError("Empty response from model")

            parsed = _extract_json(content)
            if not parsed:
                raise ValueError("Could not extract JSON from response")

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

            return {
                **match,
                "reasoning": reasoning,
            }

        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                continue
            return None


def select_fleet(
    quotes: list[dict],
    package_value: float,
    exclude: list[str] | None = None,
    intra_city: bool = False,
) -> dict:
    """
    Returns {"fleet_name", "price", "eta_hours", "reasoning"}.
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
        f"[Rule-based fallback] {choice['fleet_name']} at Rs {choice['price']} — "
        f"composite {chosen.get('composite_score', 'N/A')} "
        f"(cost {chosen.get('cost_score', 'N/A')}, time {chosen.get('time_score', 'N/A')}). "
        f"Best cost+time balance among {len(scored)} eligible options."
    )
    return {
        **choice,
        "reasoning": reasoning,
    }


def reroute_after_rto(
    quotes: list[dict],
    failed_fleet: str,
    package_value: float,
    intra_city: bool = False,
) -> dict:
    """Same selection logic, excluding the fleet(s) that just failed."""
    return select_fleet(quotes, package_value, exclude=[failed_fleet], intra_city=intra_city)
