# FleetAgent
**Autonomous Delivery Booking & Agentic Payment Settlement**

FleetAgent is an AI agent that takes a delivery order, scrapes live fleet pricing in parallel across multiple aggregators, autonomously selects the best fleet by reasoning about cost and time, holds payment through Razorpay, and — if the delivery fails (RTO) — refunds, reroutes, and retries up to 4 times, with no human in the loop.

> **This is an MVP built to demonstrate the concept, not a production system.** It's built for the Razorpay Buildathon Open Track to prove out one idea clearly: logistics booking and payment settlement can be a single autonomous decision loop, with a real payment API actually executing at the end of it — not a recommendation engine that still waits for a human to click "approve."

---

## The Problem

D2C brands, cloud kitchens, and quick-commerce sellers currently manage delivery manually: checking prices across multiple courier apps by hand, booking one, and reconciling payment separately once it's delivered. When a delivery fails and comes back (RTO — Return to Origin), that entire cycle repeats manually. RTO alone accounts for a significant share of margin loss for Indian D2C sellers during peak periods.

## The Solution

One order in, one autonomous loop:

```
Order received
   → Agent fetches live fleet quotes (parallel scraping, 4 aggregators)
   → Agent autonomously selects the best fleet and explains why
   → Payment held via Razorpay Orders API
   → Customer pays via Razorpay Checkout (test mode)
   → Delivery outcome:
        Delivered → payment released to fleet
        RTO       → payment refunded → agent reroutes to next-best fleet → retries (up to 4)
```

No manual price comparison. No manual booking. No manual reconciliation. And critically — the failure path recovers itself instead of waiting for a person to notice.

---

## What's real vs. simulated

Being precise about this is part of the point of an MVP — it shows exactly what's been proven versus what's designed but not yet buildable in this window.

| Component | Status |
|---|---|
| Fleet quote fetching (WareIQ) | **Real** — live scraping via Playwright. Results render in a modal overlay; 12+ courier quotes per pincode pair with real prices and EDD. Verified against production DOM |
| Fleet quote fetching (NimbusPost) | **Real** — live scraping via Playwright. 7+ courier quotes per pincode pair. Updated selectors for current page structure |
| Fleet quote fetching (Porter) | **Real, base-fare reference** — its live calculator is OTP-gated; using its public per-city 2-wheeler landing page instead. ETA estimated at 3h for intra-city |
| Fleet quote fetching (Borzo) | **Real** — intra-city 2-wheeler tariff, city-matched weight-bucket pricing. ETA estimated at 4h for same-day |
| Delhivery, Shiprocket | **Not integrated** — Delhivery's calculator rejects test pincodes; Shiprocket's is login-gated. Documented gap, not a silent one |
| Mock fallback | **Only when ALL scrapers fail** — mock quotes are never mixed with live ones, so the agent always reasons on real data when any scraper succeeds |
| Fleet selection reasoning | **Real & autonomous** — Groq (gpt-oss-20b) with a stateless, agentic prompt. The LLM independently derives cost-time assessments from raw price/ETA data. Composite-score rule-based fallback (cost 60% + time 40%) fires only if all 3 API retries fail |
| Category-aware selection | **Real** — quick/bike fleets are only eligible for intra-city orders; standard fleets for inter-city, so a bike courier can't win a cross-city bid |
| RTO recovery & retry | **Real** — up to 4 reroute attempts, each excluding the failed fleet. Refund processed against captured payment_id, then payment_id cleared so the new hold can collect a fresh Checkout payment |
| Payment hold (`create_hold`) | **Real** — live Razorpay Orders API call, test mode, verifiable in the Razorpay dashboard |
| Payment refund (on RTO) | **Real** — when a customer completes Razorpay Checkout and the payment_id is captured, an RTO triggers a genuine Razorpay Refund against that payment_id, verifiable in the dashboard |
| Payment release / payout to fleet | **Wired but dormant** — release_payment() calls client.payout.create() via RazorpayX, but a real payout requires an approved RazorpayX account + a registered fund_account for each fleet. Without those, it falls back to a mock payout reference. The code path is correct and ready — it is an operational prerequisite, not a design gap |
| Courier pickup/delivery itself | **Simulated** — no real truck; a "Simulate Delivered / Simulate RTO" control stands in for the webhook a real courier would send |

Any component not marked "Real" falls back automatically and safely — nothing in this build depends on an external call succeeding to keep functioning.

---

## How the AI Agent Works

The fleet selection is **stateless and autonomous** — the agent receives raw quote data (fleet name, price, ETA, category, source) and independently reasons about which fleet offers the best cost-time trade-off. No pre-computed scores are injected into the prompt; the LLM derives its own assessment.

### Selection criteria

1. **Cost efficiency** (weight 0.6) — lower price is better
2. **Time efficiency** (weight 0.4) — lower ETA is better
3. **Category constraints** — quick fleets (2-wheeler, intra-city) cannot serve inter-city routes
4. **Value assessment** — high-value packages weigh speed higher; low-value packages weigh cost higher

### Robustness

The Groq API call uses a two-phase retry strategy:
- **Attempts 1-2:** JSON mode (structured output) with `max_tokens=800`
- **Attempt 3:** No JSON mode, with manual regex extraction of the JSON object
- **Fallback:** If all retries fail, a composite-score rule (cost 60% + time 40%) picks the best fleet using the same scoring logic — not just cheapest-wins

### Example reasoning

> *"[Groq] | Cost: Price Rs 48 is competitive for same-day intra-city delivery. | Time: ETA of 3 hours ensures prompt delivery within the city. | Combining a low cost with the fastest ETA gives the best cost-time trade-off for a mid-value package."*

---

## Why Razorpay

FleetAgent isn't a logistics company — it's a demonstration of what Razorpay's payment infrastructure enables when an AI agent, not a human, is the one deciding to pay.

- **Orders API as an agent-triggered action, not a checkout step.** The payment hold in this flow is created the instant the agent picks a fleet — no human approves it. That's the same shift Razorpay's own agentic commerce work (Zomato, Swiggy, Zepto) represents on the consumer side; FleetAgent applies it to B2B vendor settlement instead.
- **The right primitive, chosen deliberately.** Early in this build, the plan was to use UPI Reserve Pay for brand-to-fleet payments. That's a consumer spending-mandate mechanism (a person authorizing an agent to pay a merchant) — the wrong fit for a brand paying a vendor. FleetAgent settled on Razorpay Orders + RazorpayX Payouts instead, the same pattern BlackBuck uses for driver disbursement at scale. Recognizing that mismatch before building around it, rather than after, is itself part of what this MVP demonstrates.
- **A real, extensible RTO recovery loop.** Refund-on-failure and reroute-on-failure are wired against Razorpay's actual Refunds API contract. After a refund, the stale `razorpay_payment_id` is cleared so the rerouted fleet's new hold can collect a fresh Checkout payment. Refunds are genuinely live (verified in the dashboard when Checkout is completed). Payouts to fleets on successful delivery are wired to RazorpayX but remain dormant until an approved RazorpayX account with registered fund accounts is configured — the last operational prerequisite, not a design gap.
- **MCP Server-ready architecture.** Razorpay's MCP Server access is approval-gated and wasn't available inside this build window, so FleetAgent calls the Razorpay Python SDK directly today. The payment layer is isolated into its own module specifically so it can be pointed at the MCP Server instead with no change to the agent or the order flow above it.

---

## Tech Stack

- **Backend:** Python, FastAPI, SQLite (SQLAlchemy), Alembic (migrations)
- **Frontend:** React 19 + Vite 8 + React Router 7 (multi-page SPA)
- **Agent reasoning:** Groq API (openai/gpt-oss-20b), free tier
- **Payments:** Razorpay Python SDK + Checkout.js, test mode
- **Fleet data:** Playwright (parallel live scraping with circuit breaker + ThreadPoolExecutor)

---

## Architecture

```
frontend/                   React 19 SPA — multi-page routed app
  src/
    main.jsx                  BrowserRouter + app entry
    App.jsx                   Routes, order list state, navigation
    api.js                    Backend API client (orders, payments, delivery)
    checkout.js               Razorpay Checkout.js opener (shared)
    pages/
      Landing.jsx             Hero, problem/solution, fleet grid, how-it-works
      OrderPage.jsx           Order form with Quick Fleets toggle
      AgentPage.jsx           Step-by-step animated agent flow (Typewriter + StepCard)
      PayoutPage.jsx          Delivery simulation, payout confirmation, events timeline
      OrdersPage.jsx          Auto-refreshing orders table (5s poll)
    components/
      Header.jsx              Sticky nav bar with active-link + order count badge
      Footer.jsx              Three-column footer
      StepCard.jsx            Animated step card (fade-in-from-left)
      Typewriter.jsx          Character-by-character text with blinking cursor

backend/
  app/
    main.py                   FastAPI app entry point, CORS, router registration
    models.py                 Order / Quote / Transaction — the state machine
    schemas.py                Pydantic API request/response contracts
    database.py               SQLAlchemy engine + session factory
    routers/
      orders.py               Order intake: quote → select → hold
      delivery.py             Delivery outcome: release / refund + reroute
      payments.py             Razorpay Checkout key + capture (signature + amount verify)
      webhooks.py             Razorpay + courier webhook endpoints (autonomous mode)
    services/
      quote_tool.py           Fleet quote scraping (Playwright, parallel + circuit breaker)
      agent_orchestrator.py    Fleet selection (Groq LLM + composite-score fallback)
      payment_tool.py         Razorpay calls (hold, refund, payout, webhook verify)
      delivery_service.py     Single source of truth for delivered/RTO state transitions
  alembic/                    Database migrations
```

### Key design principles

- **Routers stay thin, services own state.** Every router function is 1-3 lines calling a service. Business logic lives in services, so they can be tested in isolation.
- **Every external call has a fallback.** Scraper fails → mock quotes. LLM fails → rule-based composite score. Razorpay fails → mock reference. Nothing in the order flow can be broken by one flaky network call.
- **Mock quotes never mix with live.** When any scraper succeeds, only live data is returned. Mock fallback fires only when ALL scrapers fail — so the agent always reasons on real prices.
- **Single source of truth for state transitions.** Both the manual `/delivery-event` endpoint and the autonomous `/webhooks/courier` endpoint call the same `delivery_service` functions, so the RTO recovery loop, retry cap, and refund logic can never diverge.

---

## Frontend

The frontend is a multi-page React SPA built with Vite and React Router.

### Pages & flow

```
/ (Landing) ──Create Order──→ /order (OrderPage)
                                  │ submit → backend creates order + holds payment
                                  │         → opens Razorpay Checkout if keys configured
                                  ↓
                             /agent/:orderId (AgentPage)
                                  │ 4 animated step cards (Typewriter):
                                  │   1. Fetching quotes (with live quote table)
                                  │   2. AI fleet selection reasoning
                                  │   3. Razorpay payment hold
                                  │   4. Payment collection via Checkout.js
                                  │ "Proceed to Delivery"
                                  ↓
                             /payout/:orderId (PayoutPage)
                                  │ Simulate Delivered / Simulate RTO
                                  │ Payment events timeline (hold / release / refund)
                                  │ Payout confirmation banner or RTO-failed banner
                                  │
                             /orders (OrdersPage) — auto-refreshing table (5s poll)
```

### Features

- **Animated agent flow:** Step-by-step reveal with Typewriter effect and fade-in cards (1.5s between steps for readability)
- **Live quote table:** Shows fleet name, price, ETA, category (same-day/long-haul), and source (live/mock)
- **Razorpay Checkout.js integration:** Test-mode checkout with UPI/card, signature verification, and amount validation
- **Responsive design:** CSS design system with variables, responsive breakpoint at 768px

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

Open the printed Vite URL, create an order, and watch the full loop — live quotes, agent reasoning, payment hold, and (via the Simulate RTO button) the refund-and-reroute recovery with up to 4 retries.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq API key for LLM fleet selection |
| `RAZORPAY_KEY_ID` | Yes | Razorpay test-mode key ID |
| `RAZORPAY_KEY_SECRET` | Yes | Razorpay test-mode key secret |
| `RAZORPAY_X_ACCOUNT_NUMBER` | No | RazorpayX virtual account number (for real payouts) |
| `FLEET_FUND_ACCOUNTS` | No | JSON map of fleet_name → fund_account_id (for real payouts) |
| `RAZORPAY_WEBHOOK_SECRET` | No | Razorpay webhook secret (for autonomous webhook verification) |
| `COURIER_WEBHOOK_SECRET` | No | Courier webhook HMAC secret (for autonomous mode) |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/orders/` | Create order → fetch quotes → select fleet → hold payment |
| `GET` | `/orders/` | List all orders (newest first) |
| `GET` | `/orders/{id}` | Get single order with quotes and transactions |
| `POST` | `/orders/{id}/delivery-event` | Simulate Delivered or RTO (manual mode) |
| `GET` | `/payments/razorpay-key` | Get public key_id for Checkout.js |
| `POST` | `/payments/{id}/capture` | Verify Checkout signature + amount, store payment_id |
| `POST` | `/webhooks/razorpay` | Razorpay webhook (payment.captured, refund.processed, payout.processed) |
| `POST` | `/webhooks/courier` | Courier webhook (delivered, rto, picked_up) |
| `GET` | `/health` | Health check |
