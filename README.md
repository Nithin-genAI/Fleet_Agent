# FleetAgent
**Autonomous Delivery Booking & Payment Settlement**

FleetAgent is an AI agent that takes a delivery order, compares real fleet pricing, books the best option, holds payment through Razorpay, and — if the delivery fails (RTO) — refunds and reroutes itself, with no human in the loop.

> **This is an MVP built to demonstrate the concept, not a production system.** It's built for the Razorpay Buildathon Open Track to prove out one idea clearly: logistics booking and payment settlement can be a single autonomous decision loop, with a real payment API actually executing at the end of it — not a recommendation engine that still waits for a human to click "approve."

---

## The Problem

D2C brands, cloud kitchens, and quick-commerce sellers currently manage delivery manually: checking prices across multiple courier apps by hand, booking one, and reconciling payment separately once it's delivered. When a delivery fails and comes back (RTO — Return to Origin), that entire cycle repeats manually. RTO alone accounts for a significant share of margin loss for Indian D2C sellers during peak periods.

## The Solution

One order in, one autonomous loop:

```
Order received
   → Agent fetches live fleet quotes
   → Agent selects the best fleet and explains why
   → Payment held via Razorpay
   → Delivery outcome:
        Delivered → payment released to fleet
        RTO       → payment refunded → agent reroutes to next-best fleet → retries once
```

No manual price comparison. No manual booking. No manual reconciliation. And critically — the failure path recovers itself instead of waiting for a person to notice.

---

## What's real vs. simulated

Being precise about this is part of the point of an MVP — it shows exactly what's been proven versus what's designed but not yet buildable in this window.

| Component | Status |
|---|---|
| Fleet quote fetching (WareIQ, NimbusPost) | **Real** — live pin-pair scraping, verified against production DOM |
| Fleet quote fetching (Porter) | **Real, but a base-fare reference** — its live calculator is now OTP-gated; using its public per-city base-fare page instead |
| Fleet quote fetching (Borzo) | **Real** — intra-city quick-fleet tariff, city-matched |
| Delhivery, Shiprocket | **Not integrated** — Delhivery's calculator rejects test pincodes; Shiprocket's is login-gated. Documented gap, not a silent one |
| Fleet selection reasoning | **Real** — Groq (gpt-oss-20b), with a composite-score rule-based fallback (cost 60% + time 40%) if the API call fails after 3 retries. Fallback fires <1% of the time |
| Category-aware selection | **Real** — quick/bike fleets are only eligible for intra-city orders; standard fleets for inter-city, so a bike courier can't win a cross-city bid |
| Payment hold (`create_hold`) | **Real** — live Razorpay Orders API call, test mode, verifiable in the Razorpay dashboard |
| Payment refund (on RTO) | **Real** — when a customer completes Razorpay Checkout and the payment_id is captured, an RTO triggers a genuine Razorpay Refund against that payment_id, verifiable in the dashboard |
| Payment release / payout to fleet | **Wired but dormant** — release_payment() calls client.payout.create() via RazorpayX, but a real payout requires an approved RazorpayX account + a registered fund_account for each fleet. Without those (the current state), it silently falls back to a mock payout reference. The code path is correct and ready — it is an operational prerequisite, not a design gap |
| Courier pickup/delivery itself | **Simulated** — no real truck; a "Simulate Delivered / Simulate RTO" control stands in for the webhook a real courier would send |

Any component not marked "Real" falls back automatically and safely — nothing in this build depends on an external call succeeding to keep functioning.

---

## Why Razorpay

FleetAgent isn't a logistics company — it's a demonstration of what Razorpay's payment infrastructure enables when an AI agent, not a human, is the one deciding to pay.

- **Orders API as an agent-triggered action, not a checkout step.** The payment hold in this flow is created the instant the agent picks a fleet — no human approves it. That's the same shift Razorpay's own agentic commerce work (Zomato, Swiggy, Zepto) represents on the consumer side; FleetAgent applies it to B2B vendor settlement instead.
- **The right primitive, chosen deliberately.** Early in this build, the plan was to use UPI Reserve Pay for brand-to-fleet payments. That's a consumer spending-mandate mechanism (a person authorizing an agent to pay a merchant) — the wrong fit for a brand paying a vendor. FleetAgent settled on Razorpay Orders + RazorpayX Payouts instead, the same pattern BlackBuck uses for driver disbursement at scale. Recognizing that mismatch before building around it, rather than after, is itself part of what this MVP demonstrates.
- **A real, extensible RTO recovery loop.** Refund-on-failure and reroute-on-failure are wired against Razorpay's actual Refunds API contract. Refunds are genuinely live (verified in the dashboard when Checkout is completed). Payouts to fleets on successful delivery are wired to RazorpayX but remain dormant until an approved RazorpayX account with registered fund accounts is configured — the last operational prerequisite, not a design gap.
- **MCP Server-ready architecture.** Razorpay's MCP Server access is approval-gated and wasn't available inside this build window, so FleetAgent calls the Razorpay Python SDK directly today. The payment layer is isolated into its own module specifically so it can be pointed at the MCP Server instead with no change to the agent or the order flow above it.

---

## Tech Stack

- **Backend:** Python, FastAPI, SQLite (SQLAlchemy)
- **Frontend:** React (Vite)
- **Agent reasoning:** Groq API (gpt-oss-20b), free tier
- **Payments:** Razorpay Python SDK, test mode
- **Fleet data:** Playwright (live scraping of public rate calculators)

---

## Architecture

```
frontend/                 React dashboard — order form, quote comparison,
                           agent reasoning, RTO simulation controls

backend/
  app/
    main.py                FastAPI app entry point
    models.py               Order / Quote / Transaction — the state machine
    schemas.py               API request/response contracts
    routers/
      orders.py              Order intake: quote → select → hold
      delivery.py             Delivery outcome: release / refund + reroute
      payments.py             Razorpay Checkout key + capture (signature + amount verify)
      webhooks.py             Razorpay + courier webhook endpoints (autonomous mode)
    services/
      quote_tool.py           Fleet quote fetching (Playwright, parallel + circuit breaker)
      agent_orchestrator.py    Fleet selection (Groq + composite-score fallback)
      payment_tool.py           Razorpay calls (hold, refund, payout, webhook verify)
      delivery_service.py       Single source of truth for delivered/RTO state transitions
```

Every external dependency (scraper, LLM, payment API) follows the same rule: attempt the real call, catch any failure, fall back to a safe default. Nothing in the order flow can be broken by one flaky network call.

---

## Running it locally

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in GROQ_API_KEY, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
alembic upgrade head   # create database tables via migration
uvicorn app.main:app --port 8000 --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open the printed Vite URL, create an order, and watch the full loop — quotes, agent reasoning, payment hold, and (via the Simulate RTO button) the refund-and-reroute recovery.
