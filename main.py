from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from routes.pages import router as pages_router
from admin_routes import router as admin_router

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from fastapi.middleware.trustedhost import TrustedHostMiddleware
# from starlette.middleware.proxy_headers import ProxyHeadersMiddleware


app = FastAPI()

# app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
# ✅ Use proper key function (auto handles proxy if configured correctly)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "message": "Too many requests. Maximum 5 per day allowed."
        },
    )

# Mount static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(pages_router)
app.include_router(admin_router)