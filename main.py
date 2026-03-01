import os
import sys
import uvicorn
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

print(f"🔵 [MAIN] Starting application initialization...")
print(f"🔵 [MAIN] Python: {sys.version}")
print(f"🔵 [MAIN] FastAPI: importing...")

# Import routers with error handling
try:
    print("🔵 [MAIN] Importing routes.pages...")
    from routes.pages import router as pages_router
    print("✅ [MAIN] routes.pages imported successfully")
except Exception as e:
    print(f"❌ [MAIN] Failed to import routes.pages: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    print("🔵 [MAIN] Importing admin_routes...")
    from admin_routes import router as admin_router
    print("✅ [MAIN] admin_routes imported successfully")
except Exception as e:
    print(f"❌ [MAIN] Failed to import admin_routes: {e}")
    traceback.print_exc()
    sys.exit(1)

print("🔵 [MAIN] Creating FastAPI app...")

# Startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("\n" + "="*60)
    print("🚀 STARTUP: Starting BudasAI application...")
    print("="*60)
    
    try:
        print(f"📍 Environment: {'Railway' if os.getenv('RAILWAY_ENVIRONMENT') else 'Local'}")
        
        # Test currency loading
        try:
            print("🔵 Loading currency rates...")
            from utils.currency import load_currency_rates
            rates = await load_currency_rates()
            print(f"✅ Currency rates loaded: {list(rates.keys())}")
        except Exception as e:
            print(f"⚠️ Currency loading failed (will use defaults): {e}")
        
        print("✅ STARTUP: Application ready to accept requests!")
        print("="*60 + "\n")
    except Exception as e:
        print(f"❌ STARTUP FAILED: {e}")
        traceback.print_exc()
        raise
    
    yield
    
    # Shutdown
    print("\n" + "="*60)
    print("🛑 SHUTDOWN: Shutting down BudasAI application...")
    print("="*60)

print("✅ [MAIN] Creating app with lifespan...")
app = FastAPI(lifespan=lifespan)

# Request/Response logging middleware
from starlette.middleware.base import BaseHTTPMiddleware
from time import time

class DebugMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = id(request)
        start_time = time()
        
        print(f"\n{'='*70}")
        print(f"📨 REQUEST #{request_id}")
        print(f"{'='*70}")
        print(f"Method: {request.method}")
        print(f"Path: {request.url.path}")
        print(f"Query: {request.url.query}")
        print(f"Headers: {dict(request.headers)}")
        print(f"{'='*70}")
        
        try:
            response = await call_next(request)
            process_time = time() - start_time
            
            print(f"\n{'='*70}")
            print(f"📤 RESPONSE #{request_id}")
            print(f"{'='*70}")
            print(f"Status: {response.status_code}")
            print(f"Process Time: {process_time:.3f}s")
            print(f"Method: {request.method} {request.url.path}")
            print(f"{'='*70}\n")
            
            return response
        except Exception as e:
            process_time = time() - start_time
            print(f"\n{'='*70}")
            print(f"❌ ERROR IN MIDDLEWARE #{request_id}")
            print(f"{'='*70}")
            print(f"Exception: {type(e).__name__}: {str(e)}")
            print(f"Process Time: {process_time:.3f}s")
            print(f"{'='*70}")
            traceback.print_exc()
            print(f"{'='*70}\n")
            raise

app.add_middleware(DebugMiddleware)
print("✅ [MAIN] Debug middleware added")

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = id(exc)
    print(f"\n{'='*70}")
    print(f"❌ EXCEPTION #{error_id}")
    print(f"{'='*70}")
    print(f"Method: {request.method}")
    print(f"Path: {request.url.path}")
    print(f"Query: {request.url.query}")
    print(f"Exception Type: {type(exc).__name__}")
    print(f"Exception Message: {str(exc)}")
    print(f"{'='*70}")
    traceback.print_exc()
    print(f"{'='*70}\n")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "error_id": error_id,
            "path": str(request.url.path),
            "type": type(exc).__name__
        }
    )

# Health check
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "budasai"}

# Favicon
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return JSONResponse(content=None, status_code=204)

# CORS middleware
print("🔵 [MAIN] Adding CORS middleware...")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Trusted hosts middleware
print("🔵 [MAIN] Adding TrustedHost middleware...")
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# Static files
print("🔵 [MAIN] Mounting static files...")
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    print("✅ [MAIN] Static files mounted")
else:
    print("⚠️ [MAIN] static/ directory not found")

# Routers
print("🔵 [MAIN] Including routers...")
try:
    app.include_router(pages_router)
    print("✅ [MAIN] pages_router included")
except Exception as e:
    print(f"❌ [MAIN] Failed to include pages_router: {e}")
    traceback.print_exc()

try:
    app.include_router(admin_router)
    print("✅ [MAIN] admin_router included")
except Exception as e:
    print(f"❌ [MAIN] Failed to include admin_router: {e}")
    traceback.print_exc()

print("\n✅ [MAIN] Application initialization complete!")
print("🔵 [MAIN] Waiting for Uvicorn to start server...\n")

if __name__ == "__main__":
    # Use PORT env variable if set by Railway, otherwise default to 8000
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting Uvicorn server on http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
print("✅ Admin router registered")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting BudasAI server on 0.0.0.0:{port}")
    print(f"📍 Environment: {'Production' if os.getenv('RAILWAY_ENVIRONMENT') else 'Development'}")
    uvicorn.run("main:app", host="0.0.0.0", port=port)