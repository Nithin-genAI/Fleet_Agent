from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import orders, delivery

Base.metadata.create_all(bind=engine)  # creates fleetagent.db + tables on first run

app = FastAPI(title="FleetAgent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for a hackathon demo; scope this down for anything real
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.router)
app.include_router(delivery.router)


@app.get("/health")
def health():
    return {"status": "ok"}
