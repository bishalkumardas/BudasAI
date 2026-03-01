import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from routes.pages import router as pages_router
from admin_routes import router as admin_router

app = FastAPI()

# Startup event to verify critical dependencies
@app.on_event("startup")
async def startup_event():
    print("🚀 Starting BudasAI application...")
    print(f"📍 Environment: {'Railway' if os.getenv('RAILWAY_ENVIRONMENT') else 'Local'}")
    
    # Test currency loading (with fallback)
    try:
        from utils.currency import load_currency_rates
        rates = await load_currency_rates()
        print(f"✅ Currency rates loaded: {list(rates.keys())}")
    except Exception as e:
        print(f"⚠️ Currency rate loading issue (will use defaults): {e}")
    
    print("✅ Application startup complete!")

# Health check endpoint for Railway
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": "ok"}

# Routers
app.include_router(pages_router)
app.include_router(admin_router)

for route in app.routes:
    print(f"Path: {route.path} | Name: {route.name}")

# Static files
if os.path.isdir("static"):
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
    allowed_hosts=["*"] # Use quotes to make it a string
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting BudasAI server on 0.0.0.0:{port}")
    print(f"📍 Environment: {'Production' if os.getenv('RAILWAY_ENVIRONMENT') else 'Development'}")
    uvicorn.run("main:app", host="0.0.0.0", port=port)