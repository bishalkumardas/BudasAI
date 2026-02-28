import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from routes.pages import router as pages_router
from admin_routes import router as admin_router

app = FastAPI()

# Routers
app.include_router(pages_router)
app.include_router(admin_router)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # replace with your domain later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Trusted hosts
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["budasai.com", "www.budasai.com", "localhost"]
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)