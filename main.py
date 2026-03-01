import os
import uvicorn
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, FileResponse

from routes.pages import router as pages_router
from admin_routes import router as admin_router

# Startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting BudasAI application...")
    print(f"📍 Environment: {'Railway' if os.getenv('RAILWAY_ENVIRONMENT') else 'Local'}")
    
    # Test currency loading (with fallback)
    try:
        from utils.currency import load_currency_rates
        rates = await load_currency_rates()
        print(f"✅ Currency rates loaded: {list(rates.keys())}")
    except Exception as e:
        print(f"⚠️ Currency rate loading issue (will use defaults): {e}")
        traceback.print_exc()
    
    print("✅ Application startup complete!")
    yield
    # Shutdown
    print("🛑 Shutting down BudasAI application...")

app = FastAPI(lifespan=lifespan)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"❌ Unhandled exception on {request.method} {request.url.path}")
    print(f"Error: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "path": str(request.url.path)}
    )

# Health check endpoint for Railway
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": "ok"}

# Favicon handler
@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content=None, status_code=204)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Trusted hosts middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# Static files mount
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    print("✅ Static files mounted")

# Include routers
print("📌 Registering routes...")
app.include_router(pages_router)
print("✅ Pages router registered")
app.include_router(admin_router)
print("✅ Admin router registered")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting BudasAI server on 0.0.0.0:{port}")
    print(f"📍 Environment: {'Production' if os.getenv('RAILWAY_ENVIRONMENT') else 'Development'}")
    uvicorn.run("main:app", host="0.0.0.0", port=port)