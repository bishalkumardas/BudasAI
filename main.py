from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from routes.pages import router as pages_router
from admin_routes import router as admin_router

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

import os
import uvicorn

app = FastAPI()

# ✅ Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"success": False, "message": "Too many requests. Maximum 5 per day allowed."},
    )

# ✅ Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # replace with your domain(s) later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Trusted hosts
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["budasai.com", "www.budasai.com", "localhost"]
)

# ✅ Routers
app.include_router(pages_router)
app.include_router(admin_router)

# ✅ Uvicorn run
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)  # reload=True only for local dev