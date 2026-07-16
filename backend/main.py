from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from api.routes import (
    agent_chat,
    agent_share,
    agents,
    chat_sessions,
    project_files,
    projects,
    public_chat,
)
from db.session import engine
from observability.otel import configure_otel
from temporal.client import close_temporal_client, init_temporal_client

# Bootstrap OTel before the app object is created so the FastAPI instrumentor
# can attach to the already-configured tracer provider.
configure_otel("aktilot-api")
SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_temporal_client()
    yield
    close_temporal_client()


app = FastAPI(title="Document AI Assistant", lifespan=lifespan)

FastAPIInstrumentor.instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(project_files.router)
app.include_router(agents.project_router)
app.include_router(agents.agent_router)
app.include_router(agent_chat.router)
app.include_router(agent_share.router)
app.include_router(chat_sessions.router)
app.include_router(public_chat.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
