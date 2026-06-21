from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import files, chunks, chat, projects, project_files, agents, agent_chat

app = FastAPI(title="Document AI Assistant")

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
app.include_router(files.router)
app.include_router(chunks.router)
app.include_router(chat.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
