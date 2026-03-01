from datetime import datetime, timedelta
import json
import traceback
import httpx
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from database import supabase
import os
import html
from jose import JWTError, jwt
from auth import SECRET_KEY, ALGORITHM


# pricing utilities
# from utils.currency import get_price_context

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # ctx = await get_price_context(request)
    ctx = {}
    return templates.TemplateResponse("home.html", {"request": request, **ctx})


@router.get("/products", response_class=HTMLResponse)
async def products(request: Request):
    ctx = await get_price_context(request)
    return templates.TemplateResponse("products.html", {"request": request, **ctx})


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    ctx = await get_price_context(request)
    return templates.TemplateResponse("admin.html", {"request": request, **ctx})


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    ctx = await get_price_context(request)
    return templates.TemplateResponse("admin.html", {"request": request, **ctx})



# SECRET_KEY = "SUPER_SECRET_ADMIN_KEY"
# ALGORITHM = "HS256"

# def check_auth(request: Request):
#     token = request.cookies.get("admin_token")
#     if not token:
#         return False
#     try:
#         # This MUST use the same SECRET_KEY as auth.py
#         jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         return True
#     except:
#         return False


@router.get("/download-guide")
async def download_guide(request: Request):
    # Check if the CUSTOMER is logged in (using the Supabase token)
    token = request.cookies.get("sb-access-token")
    
    if not token:
        # Redirect back to the page they came from, adding a 'login=required' flag
        return RedirectResponse(url="/products?login=required", status_code=303)

    try:
        # If logged in, get the file
        res = supabase.storage.from_("PDFs").create_signed_url(
            "BudasAI Insight Feb 2026.pdf", 60
        )
        return RedirectResponse(url=res["signedURL"], status_code=303)
    except Exception as e:
        return HTMLResponse(f"Error: {e}")


@router.get("/story", response_class=HTMLResponse)
async def story(request: Request):
    response = supabase.table("stories").select("*").order("id", desc=True).execute()
    stories_list = response.data or []
    
    sanitized = []
    for s in stories_list:
        try:
            if not isinstance(s, dict):
                continue
            is_pub = s.get("is_published") or s.get("is_publish")
            if is_pub:
                res = s.get("results", {})
                if isinstance(res, str):
                    try:
                        res = json.loads(res)
                    except:
                        res = {"raw": res}
                s["results"] = res or {}
                sanitized.append(s)
        except Exception as e:
            print(f"Error: {e}")

    ctx = await get_price_context(request)
    return templates.TemplateResponse("story.html", {"request": request, "stories": sanitized, **ctx})


@router.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    response = supabase.table("blogs").select("*").order("date", desc=True).execute()
    blogs_list = response.data or []
    
    published = []
    for b in blogs_list:
        try:
            if not isinstance(b, dict):
                continue
            is_pub = b.get("is_published") or b.get("is_publish")
            if is_pub:
                b.setdefault("image_url", "")
                b.setdefault("excerpt", "")
                b.setdefault("date", "")
                b.setdefault("slug", "")
                published.append(b)
        except:
            pass

    ctx = await get_price_context(request)
    return templates.TemplateResponse("blog.html", {"request": request, "blogs": published, **ctx})


@router.get("/blog/{id}", response_class=HTMLResponse)
async def full_blog(request: Request, id: int):
    response = supabase.table("blogs").select("*").eq("id", id).single().execute()
    if not response.data:
        raise HTTPException(status_code=404)
    
    blog_data = response.data
    is_pub = blog_data.get("is_published") or blog_data.get("is_publish")
    if not is_pub:
        raise HTTPException(status_code=404)
    
    blog_data.setdefault("html_content", "")
    ctx = await get_price_context(request)
    return templates.TemplateResponse("full_blog.html", {"request": request, "blog": blog_data, **ctx})


@router.get("/auth/callback")
async def auth_callback():
    return HTMLResponse("""
    <html><body><script>
        const hash = window.location.hash;
        if (hash.includes('access_token=')) {
            const params = new URLSearchParams(hash.substring(1));
            fetch('/set-auth-token', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    accessToken: params.get('access_token'),
                    refreshToken: params.get('refresh_token')
                })
            }).then(() => window.location.href = '/');
        } else {
            window.location.href = '/';
        }
    </script><p>Authenticating...</p></body></html>
    """)


@router.get("/get-user")
async def get_user(request: Request):
    token = request.cookies.get("sb-access-token")
    if not token:
        return {"user": None}
    user = supabase.auth.get_user(token)
    return {"user": user.user} if user and user.user else {"user": None}


@router.post("/set-auth-token")
async def set_auth_token(request: Request):
    body = await request.json()
    response = JSONResponse({"success": True})
    response.set_cookie("sb-access-token", body.get("accessToken", ""), httponly=True, max_age=3600)
    response.set_cookie("sb-refresh-token", body.get("refreshToken", ""), httponly=True, max_age=604800)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sb-refresh-token")
    return response


RESEND_API_KEY = os.getenv("RESEND_API_KEY")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
SENDER_EMAIL = "bishaldas@budasai.com"


@router.post("/contact")
async def contact(request: Request):
    form_data = await request.form()

    name = form_data.get("name")
    email = form_data.get("email")
    business_type = form_data.get("business_type")
    message = form_data.get("message")

    print("Form received:", dict(form_data))


@router.get("/health")
def health():
    return {"status": "ok"}


# @router.get("/download-guide")
# async def download_guide():
#     return {"status": "Route is definitely registered!"}