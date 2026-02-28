from datetime import datetime
from email.mime import message
import json
import traceback
import httpx
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from database import supabase
import os
from slowapi import Limiter
from slowapi.util import get_remote_address
import html

# pricing utilities
from utils.currency import get_price_context

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    ctx = await get_price_context(request)
    return templates.TemplateResponse("home.html", {"request": request, **ctx})


# @router.get("/story", response_class=HTMLResponse)
# async def story(request: Request):
#     return templates.TemplateResponse("story.html", {"request": request})


@router.get("/products", response_class=HTMLResponse)
async def products(request: Request):
    ctx = await get_price_context(request)
    return templates.TemplateResponse("products.html", {"request": request, **ctx})


# @router.get("/blog", response_class=HTMLResponse)
# async def blog(request: Request):
#     return templates.TemplateResponse("blog.html", {"request": request})

# @router.get("/full_blog", response_class=HTMLResponse)
# async def full_blog(request: Request):
#     return templates.TemplateResponse("full_blog.html", {"request" : request})


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    ctx = await get_price_context(request)
    return templates.TemplateResponse("about.html", {"request": request, **ctx})

@router.get("/admin", response_class=HTMLResponse)
async def about(request: Request):
    ctx = await get_price_context(request)
    return templates.TemplateResponse("admin.html", {"request": request, **ctx})


@router.get("/story", response_class=HTMLResponse)
async def story(request: Request):
    # Fetch all stories without assuming column name, then filter in Python
    response = supabase.table("stories")\
        .select("*")\
        .order("id", desc=True)\
        .execute()

    stories_list = response.data or []
    try:
        count_total = len(stories_list)
    except Exception:
        count_total = 0

    # Keep only published stories regardless of DB column name
    sanitized = []
    for s in stories_list:
        try:
            if not isinstance(s, dict):
                continue

            # determine published flag from either column
            is_pub = s.get("is_published")
            if is_pub is None:
                is_pub = s.get("is_publish")
            if is_pub:
                # normalize results into dict
                res = s.get("results", {})
                if isinstance(res, str):
                    try:
                        res = json.loads(res)
                    except Exception:
                        res = {"raw": res}
                if res is None:
                    res = {}
                s["results"] = res
                sanitized.append(s)
        except Exception as e:
            print(f"Error processing story record: {e}")

    # print(f"[public] /story -> total={count_total}, published={len(sanitized)}")

    try:
        ctx = await get_price_context(request)
        return templates.TemplateResponse(
            "story.html",
            {
                "request": request,
                "stories": sanitized,
                **ctx
            }
        )
    except Exception as e:
        print("Error rendering story template:", e)
        traceback.print_exc()
        ctx = await get_price_context(request)
        return templates.TemplateResponse(
            "story.html",
            {"request": request, "stories": [], **ctx}
        )


@router.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    # Fetch all blogs and filter published in Python to avoid column-name mismatch
    response = supabase.table("blogs")\
        .select("*")\
        .order("date", desc=True)\
        .execute()

    blogs_list = response.data or []
    try:
        total = len(blogs_list)
    except Exception:
        total = 0

    published = []
    for b in blogs_list:
        try:
            if not isinstance(b, dict):
                continue

            is_pub = b.get("is_published")
            if is_pub is None:
                is_pub = b.get("is_publish")

            if is_pub:
                # ensure essential keys exist
                b.setdefault("image_url", "")
                b.setdefault("excerpt", "")
                b.setdefault("date", "")
                b.setdefault("slug", "")

                # ---------- DATE FORMAT FIX ----------
                if b.get("date"):
                    try:
                        b["date"] = datetime.strptime(
                            b["date"], "%Y-%m-%d"
                        ).strftime("%B %d, %Y").replace(" 0", " ")
                    except Exception:
                        pass
                # -------------------------------------

                published.append(b)

        except Exception as e:
            print(f"Error processing blog record: {e}")

    # print(f"[public] /blog -> total={total}, published={len(published)}")

    # Debug: if ?raw=1 is provided, return JSON of rows for inspection
    if request.query_params.get("raw") == "1":
        try:
            sample_keys = list(published[0].keys()) if published else []
        except Exception:
            sample_keys = []
        print(f"[public] /blog debug keys: {sample_keys}")
        return JSONResponse({"total": total, "published": len(published), "rows": published})

    ctx = await get_price_context(request)
    return templates.TemplateResponse(
        "blog.html",
        {
            "request": request,
            "blogs": published,
            **ctx
        }
    )


@router.get("/blog/{id}", response_class=HTMLResponse)
async def full_blog(request: Request, id: int):
    # Fetch by id and check published flag in Python
    response = supabase.table("blogs")\
        .select("*")\
        .eq("id", id)\
        .single()\
        .execute()

    if not response.data:
        raise HTTPException(status_code=404)

    blog_data = response.data
    is_pub = blog_data.get("is_published")
    if is_pub is None:
        is_pub = blog_data.get("is_publish")
    if not is_pub:
        raise HTTPException(status_code=404)

    # normalize html_content
    blog_data.setdefault("html_content", "")

    ctx = await get_price_context(request)
    return templates.TemplateResponse(
        "full_blog.html",
        {
            "request": request,
            "blog": blog_data,
            **ctx
        }
    )

# user login and auth routes are in admin_routes.py, which is included in main.py
@router.get("/auth/callback")
async def auth_callback():
    # This endpoint renders a page with JS that handles the OAuth callback
    # The hash fragment is preserved in the client and extracted by JavaScript
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Authenticating...</title>
    </head>
    <body>
        <script>
            async function handleCallback() {
                const hash = window.location.hash;
                console.log('OAuth callback - hash:', hash.substring(0, 50) + '...');
                
                if (hash.includes('access_token=')) {
                    const params = new URLSearchParams(hash.substring(1));
                    const accessToken = params.get('access_token');
                    const refreshToken = params.get('refresh_token');
                    
                    console.log('Extracted tokens - Access:', !!accessToken, 'Refresh:', !!refreshToken);
                    
                    if (accessToken && refreshToken) {
                        try {
                            console.log('Sending tokens to /set-auth-token');
                            const response = await fetch('/set-auth-token', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ 
                                    accessToken: accessToken,
                                    refreshToken: refreshToken 
                                })
                            });
                            console.log('Set token response:', response.ok);
                            if (response.ok) {
                                window.location.href = '/';
                            }
                        } catch (error) {
                            console.error('Auth error:', error);
                            window.location.href = '/';
                        }
                    }
                } else {
                    console.log('No access token in hash, redirecting home');
                    window.location.href = '/';
                }
            }
            handleCallback();
        </script>
        <p>Authenticating...</p>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

@router.get("/get-user")
async def get_user(request: Request):
    token = request.cookies.get("sb-access-token")

    if not token:
        return {"user": None}

    user = supabase.auth.get_user(token)

    if not user or not user.user:
        return {"user": None}

    return {"user": user.user}


@router.post("/set-auth-token")
async def set_auth_token(request: Request):
    body = await request.json()
    access_token = body.get("accessToken")
    refresh_token = body.get("refreshToken")
    
    if not access_token or not refresh_token:
        return {"success": False}
    
    response = JSONResponse({"success": True})
    response.set_cookie("sb-access-token", access_token, httponly=True, max_age=3600)
    response.set_cookie("sb-refresh-token", refresh_token, httponly=True, max_age=604800)
    
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sb-refresh-token")
    return response


@router.get("/download/guide")
async def download_guide(request: Request):
    token = request.cookies.get("sb-access-token")

    if not token:
        return RedirectResponse("/login")

    return FileResponse("static/files/guide.pdf")


@router.get("/download-audit-report")
async def download_audit_report(request: Request):
    token = request.cookies.get("sb-access-token")

    if not token:
        return RedirectResponse("/")

    # Fetch PDF from Supabase storage
    supabase_url = "https://aznlbmkbuwasvaqrnnfo.supabase.co/storage/v1/object/public/PDFs/BudasAI%20Insight%20Feb%202026.pdf"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(supabase_url)
        
        if response.status_code == 200:
            return Response(
                content=response.content,
                media_type="application/pdf",
                headers={"Content-Disposition": "attachment; filename=BudasAI_free_test.pdf"}
            )
        else:
            return {"error": "Failed to download PDF"}
    except Exception as e:
        print(f"Download error: {e}")
        return {"error": "Download failed"}
    

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
SENDER_EMAIL = "bishaldas@budasai.com"
limiter = Limiter(key_func=get_remote_address)


@router.post("/contact")
@limiter.limit("5/day")
async def contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    business_type: str = Form(...),
    message: str = Form(...)
):
    try:
        # ----------------------------
        # 1️⃣ Basic Validation
        # ----------------------------

        if len(name) > 100:
            return JSONResponse({"success": False, "message": "Invalid name"})

        if len(message) > 2000:
            return JSONResponse({"success": False, "message": "Message too long"})

        blocked_words = ["http://", "https://", "viagra", "casino"]
        if any(word in message.lower() for word in blocked_words):
            return JSONResponse({"success": False, "message": "Spam detected"})

        # ----------------------------
        # 2️⃣ Escape HTML (Security)
        # ----------------------------

        safe_name = html.escape(name)
        safe_email = html.escape(email)
        safe_business = html.escape(business_type)
        safe_message = html.escape(message)

        # ----------------------------
        # 3️⃣ Send Emails
        # ----------------------------

        async with httpx.AsyncClient(timeout=30) as client:

            # Admin email
            admin_response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": f"BudasAI <{SENDER_EMAIL}>",  # must be verified domain
                    "to": ADMIN_EMAIL,
                    "subject": f"BudasAI client {safe_name}",
                    "html": f"""
                        <h3>New Lead Submission</h3>
                        <p><b>Name:</b> {safe_name}</p>
                        <p><b>Email:</b> {safe_email}</p>
                        <p><b>Business Type:</b> {safe_business}</p>
                        <p><b>Message:</b><br>{safe_message}</p>
                        <p><i>Submitted at: {datetime.utcnow().isoformat()} UTC</i></p>
                    """
                }
            )

            if admin_response.status_code != 200:
                print("Admin email failed:", admin_response.text)
                return JSONResponse({"success": False, "message": "Email failed"})

            # Client confirmation email
            client_response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": f"BudasAI <{SENDER_EMAIL}>",
                    "to": safe_email,
                    "subject": f"Your message has been sent, {safe_name}",
                    "html": f"""
                        <h3>Hi {safe_name},</h3>
                        <p>Thank you for contacting BudasAI.</p>
                        <p>We have received your message and will respond within 24 hours.</p>
                        <h4>Your Submission:</h4>
                        <p><b>Business Type:</b> {safe_business}</p>
                        <p><b>Message:</b><br>{safe_message}</p>
                        <br>
                        <p>— Team BudasAI</p>
                    """
                }
            )

            if client_response.status_code != 200:
                print("Client email failed:", client_response.text)
                return JSONResponse({"success": False, "message": "Confirmation failed"})

        # ----------------------------
        # 4️⃣ Save to Supabase
        # ----------------------------

        result = supabase.table("leads").insert({
            "name": safe_name,
            "email": safe_email,
            "business_type": safe_business,
            "message": safe_message,
            "ip_address": request.client.host,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        # print("Supabase insert result:", result)

        return JSONResponse({"success": True})

    except Exception as e:
        print("Contact error:", e)
        traceback.print_exc()
        return JSONResponse({"success": False, "message": "Server error"})
    
    
