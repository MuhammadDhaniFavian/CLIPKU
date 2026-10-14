"""
CliperKu - Aplikasi Utama FastAPI.
Aturan Keamanan:
- Mengikat secara ketat hanya ke 127.0.0.1
- CORS dibatasi secara spesifik hanya untuk frontend lokal
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.video import router as video_router
from app.core.config import HOST, PORT, FRONTEND_URL

app = FastAPI(
    title="CliperKu API",
    description="Backend lokal untuk AI Auto Clipper video panjang ke pendek",
    version="0.2.0"
)

# CORS ketat hanya untuk frontend lokal
origins = [
    FRONTEND_URL,
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(video_router)


@app.get("/")
def root():
    return {
        "app": "CliperKu",
        "version": "0.2.0 (Fase 2 MVP)",
        "status": "ready",
        "mode": "offline-local"
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)

