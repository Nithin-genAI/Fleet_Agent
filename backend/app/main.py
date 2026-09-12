from dotenv import load_dotenv
load_dotenv()  # must run before anything reads os.environ (Groq/Razorpay clients read lazily, but this is the standard place)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine

from .routers import orders, delivery, payments, webhooks

# Schema is managed by Alembic migrations — run `alembic upgrade head` to create
# tables. This create_all is a safety net for dev: if no migration has been run
# yet (e.g. fresh clone without alembic), it creates the tables so the app
# still starts. In production, use Alembic exclusively.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="FleetAgent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for a hackathon demo; scope this down for anything real
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.router)
app.include_router(delivery.router)
app.include_router(payments.router)
app.include_router(webhooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}
