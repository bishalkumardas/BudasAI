from datetime import datetime
import json
import re
# import traceback
# import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import  FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from database import supabase
import os
import html
# from jose import JWTError, jwt
# from auth import SECRET_KEY, ALGORITHM


# pricing utilities
from utils.currency import get_price_context

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Add this near the top of pages.py
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    route_id = id(request)
    try:
        # print(f"\n🔵 [HOME ROUTE #{route_id}] Starting...")
        
        # print(f"🔵 [HOME ROUTE #{route_id}] Calling get_price_context...")
        ctx = await get_price_context(request)
        # print(f"🔵 [HOME ROUTE #{route_id}] Price context: {ctx}")
        
        # print(f"🔵 [HOME ROUTE #{route_id}] Rendering template...")
        response = templates.TemplateResponse("home.html", {"request": request, **ctx})
        # print(f"✅ [HOME ROUTE #{route_id}] Successfully rendered")
        
        return response
    except Exception as e:
        print(f"❌ [HOME ROUTE #{route_id}] Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return basic fallback
        print(f"🔵 [HOME ROUTE #{route_id}] Using fallback template...")
        try:
            return templates.TemplateResponse(
                "home.html", 
                {
                    "request": request, 
                    "currency": "INR", 
                    "price": 4999, 
                    "adv_price": 14999, 
                    "symbol": "₹"
                }
            )
        except Exception as e2:
            print(f"❌ [HOME ROUTE #{route_id}] Fallback also failed: {e2}")
            return HTMLResponse(
                f"<html><body><h1>Error</h1><p>{str(e)}</p><p>{str(e2)}</p></body></html>",
                status_code=500
            )


@router.get("/products", response_class=HTMLResponse)
async def products(request: Request):
    try:
        ctx = await get_price_context(request)
        return templates.TemplateResponse("products.html", {"request": request, **ctx})
    except Exception as e:
        print(f"Error in products route: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("products.html", {"request": request, "currency": "INR", "price": 4999, "adv_price": 14999, "symbol": "₹"})


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    try:
        ctx = await get_price_context(request)
        return templates.TemplateResponse("admin.html", {"request": request, **ctx})
    except Exception as e:
        print(f"Error in admin route: {e}")
        return templates.TemplateResponse("admin.html", {"request": request, "currency": "INR", "price": 4999, "adv_price": 14999, "symbol": "₹"})


@router.get("/about")
async def about(request:Request):
    try:
        ctx = await get_price_context(request)
        return templates.TemplateResponse("about.html", {"request": request, **ctx})
    except Exception as e:
        print(f"Error in about route: {e}")
        return templates.TemplateResponse("about.html", {"request": request, "currency": "INR", "price": 4999, "adv_price": 14999, "symbol": "₹"})



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
    try:
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
                print(f"Error processing story: {e}")

        ctx = await get_price_context(request)
        return templates.TemplateResponse("story.html", {"request": request, "stories": sanitized, **ctx})
    except Exception as e:
        print(f"Error in story route: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("story.html", {"request": request, "stories": [], "currency": "INR", "price": 4999, "adv_price": 14999, "symbol": "₹"})


@router.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    try:
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

                    # FORMAT DATE
                    if b.get("date"):
                        try:
                            dt = datetime.fromisoformat(str(b["date"]))
                            b["date"] = dt.strftime("%B %d, %Y")   # March 02, 2026
                        except:
                            pass

                    b["clean_title"] = clean_title_for_url(b.get("title", ""))
                    published.append(b)
            except:
                pass

        ctx = await get_price_context(request)
        return templates.TemplateResponse("blog.html", {"request": request, "blogs": published, **ctx})
    except Exception as e:
        print(f"Error in blog route: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("blog.html", {"request": request, "blogs": [], "currency": "INR", "price": 4999, "adv_price": 14999, "symbol": "₹"})



def clean_title_for_url(title: str) -> str:
    title = title.lower()
    title = re.sub(r'[^a-z0-9\s-]', '', title)   # remove special characters
    title = re.sub(r'\s+', '-', title)           # spaces -> hyphen
    title = re.sub(r'-+', '-', title)            # remove double hyphens
    return title.strip('-')


@router.get("/blog/{id}", response_class=HTMLResponse)
async def full_blog_redirect(request: Request, id: int):
    try:
        response = (
            supabase.table("blogs")
            .select("title")
            .eq("id", id)
            .single()
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404)

        correct_title = clean_title_for_url(response.data["title"])

        return RedirectResponse(
            url=f"/blog/{id}/{correct_title}",
            status_code=301
        )

    except Exception as e:
        print("Redirect error:", e)
        raise HTTPException(status_code=404)
    

@router.get("/blog/{id}/{title}", response_class=HTMLResponse)
async def full_blog(request: Request, id: int, title: str):
    try:
        response = (
            supabase.table("blogs")
            .select("*")
            .eq("id", id)
            .single()
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404)

        blog_data = response.data

        if not blog_data.get("is_publish"):
            raise HTTPException(status_code=404)

        # --- SEO redirect (important) ---
        correct_title = clean_title_for_url(blog_data["title"])
        if title != correct_title:
            return RedirectResponse(
                url=f"/blog/{id}/{correct_title}",
                status_code=301
            )

        blog_data.setdefault("html_content", "")

        # FORMAT DATE (ADD THIS BLOCK)
        if blog_data.get("date"):
            try:
                dt = datetime.fromisoformat(str(blog_data["date"]))
                blog_data["date"] = dt.strftime("%B %d, %Y").replace(" 0", " ")
            except:
                pass

        ctx = await get_price_context(request)

        return templates.TemplateResponse(
            "full_blog.html",
            {"request": request, "blog": blog_data, **ctx}
        )

    except HTTPException:
        raise
    except Exception as e:
        print("Blog error:", e)
        raise HTTPException(status_code=500)


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
    try:
        token = request.cookies.get("sb-access-token")
        if not token:
            return {"user": None}
        user = supabase.auth.get_user(token)
        return {"user": user.user} if user and user.user else {"user": None}
    except Exception as e:
        print(f"Error in get-user route: {e}")
        return {"user": None}


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
    try:
        form_data = await request.form()

        name = form_data.get("name")
        email = form_data.get("email")
        business_type = form_data.get("business_type")
        message = form_data.get("message")

        print("Form received:", dict(form_data))
        
        # TODO: Implement email sending logic
        return JSONResponse({"success": True, "message": "Contact form received"})
    except Exception as e:
        print(f"Contact form error: {e}")
        return JSONResponse({"success": False, "message": "Error processing form"}, status_code=500)



@router.get("/term-condition", response_class=HTMLResponse)
async def term_condition(request: Request):
    # print(datetime.now().strftime("%B %d, %Y"))
    return templates.TemplateResponse(
        "payment_terms.html",
        {
            "request": request,
            "now": datetime.now().strftime("%B %d, %Y")
        }
    )
@router.get("/ads.txt")
async def ads():
    return FileResponse("ads.txt", media_type="text/plain")

# @router.get("/download-guide")
# async def download_guide():
#     return {"status": "Route is definitely registered!"}
