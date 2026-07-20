from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .app_current import app as current_app
from .app_trace import app as trace_app

app = FastAPI(title="FPT Telecom OTDR - Unified Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/current", current_app)
app.mount("/trace", trace_app)

@app.get("/")
def read_root():
    return {"message": "Unified OTDR Backend API is running"}
