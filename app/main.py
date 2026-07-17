import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.alerts import start_scheduler
from app.database import Base, engine, run_auto_migrations
from app.routers import auth, subcontractors, projects, documents, dashboard, packets, clients

logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)
run_auto_migrations()

app = FastAPI(
    title="SubDox API",
    description="Subcontractor compliance management backend: subcontractors, "
                "document uploads, compliance tracking, and expiry alerts.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(subcontractors.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(dashboard.router)
app.include_router(packets.router)
app.include_router(clients.router)

_scheduler = None


@app.on_event("startup")
def on_startup():
    global _scheduler
    _scheduler = start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    if _scheduler:
        _scheduler.shutdown(wait=False)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
