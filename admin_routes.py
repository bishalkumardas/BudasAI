from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from database import supabase
from auth import verify_password, create_token
from jose import jwt, JWTError
import os
import json
import traceback
from datetime import datetime
from urllib.parse import urlencode
from dotenv import load_dotenv

# pricing helpers
from utils.currency import get_price_context

load_dotenv()

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL_ADDRESS")

def check_auth(request: Request):
    token = request.cookies.get("admin_token")

    if not token:
        raise HTTPException(status_code=401)

    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401)
    

@router.get("/admin/login")
async def admin_login_page(request: Request):
    ctx = await get_price_context(request)
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "error": None, **ctx}
    )


@router.post("/admin/login")
async def admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):

    if email != ADMIN_EMAIL:
        ctx = await get_price_context(request)
        return templates.TemplateResponse(
            "admin.html",
            {"request": request, "error": "Invalid email address", **ctx}
        )

    if not verify_password(password):
        ctx = await get_price_context(request)
        return templates.TemplateResponse(
            "admin.html",
            {"request": request, "error": "Invalid password", **ctx}
        )

    token = create_token()

    response = RedirectResponse(
        url="/admin/dashboard",
        status_code=302
    )

    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        max_age=60*60*8
    )

    return response


@router.get("/admin/dashboard")
async def admin_dashboard(
    request: Request,
    auth=Depends(check_auth)
):
    # Fetch all blogs and stories from Supabase
    try:
        blogs_data = supabase.table("blogs").select("*").execute()
        blogs = blogs_data.data if blogs_data.data else []
    except Exception as e:
        blogs = []
    
    try:
        stories_data = supabase.table("stories").select("*").execute()
        stories = stories_data.data if stories_data.data else []
    except Exception as e:
        stories = []

    try:
        ai_tools_data = (
            supabase
            .table("ai_tools")
            .select("*")
            .order("display_order", desc=False)
            .execute()
        )
        ai_tools = ai_tools_data.data if ai_tools_data.data else []
    except Exception:
        ai_tools = []
    
    ctx = await get_price_context(request)
    status = request.query_params.get("status")
    message = request.query_params.get("message")
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "blogs": blogs,
            "stories": stories,
            "ai_tools": ai_tools,
            "admin_status": status,
            "admin_message": message,
            **ctx
        }
    )


def admin_redirect(status: str, message: str) -> RedirectResponse:
    query = urlencode({"status": status, "message": message})
    return RedirectResponse(f"/admin/dashboard?{query}", status_code=302)


def parse_checkbox_flag(value: str | bool | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"on", "true", "1", "yes", "y", "t"}
    return default


def parse_score(value: str | float | int | None, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def parse_optional_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = int(raw)
            return parsed if parsed > 0 else None
        except ValueError:
            return None
    return None


def get_next_display_order() -> int:
    try:
        res = (
            supabase
            .table("ai_tools")
            .select("display_order")
            .order("display_order", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return 1
        current_max = int(rows[0].get("display_order") or 0)
        return current_max + 1
    except Exception:
        return 1


@router.post("/admin/aitool/create")
async def create_ai_tool(
    request: Request,
    name: str = Form(...),
    best_for: str = Form(default=""),
    image_url: str = Form(default=""),
    quality_score: float = Form(default=0),
    ease_score: float = Form(default=0),
    accuracy_score: float = Form(default=0),
    speed_score: float = Form(default=0),
    value_score: float = Form(default=0),
    creativity_score: float = Form(default=0),
    integration_score: float = Form(default=0),
    consistency_score: float = Form(default=0),
    support_score: float = Form(default=0),
    time_saved_score: float = Form(default=0),
    display_order: str = Form(default=""),
    is_active: str = Form(default=""),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Creating AI tool: {name}")
        resolved_display_order = parse_optional_int(display_order)
        if resolved_display_order is None:
            resolved_display_order = get_next_display_order()

        payload = {
            "name": name,
            "best_for": best_for,
            "image_url": image_url,
            "quality_score": parse_score(quality_score),
            "ease_score": parse_score(ease_score),
            "accuracy_score": parse_score(accuracy_score),
            "speed_score": parse_score(speed_score),
            "value_score": parse_score(value_score),
            "creativity_score": parse_score(creativity_score),
            "integration_score": parse_score(integration_score),
            "consistency_score": parse_score(consistency_score),
            "support_score": parse_score(support_score),
            "time_saved_score": parse_score(time_saved_score),
            "display_order": resolved_display_order,
            "is_active": parse_checkbox_flag(is_active, default=False),
            "updated_at": datetime.now().isoformat(),
        }
        response = supabase.table("ai_tools").insert(payload).execute()
        print(f"✅ AI tool created successfully: {response}")
    except Exception as e:
        print(f"❌ Error creating AI tool: {str(e)}")
        traceback.print_exc()
        return admin_redirect("error", "Failed to create AI tool. Check logs and values.")

    return admin_redirect("success", f"AI tool '{name}' created successfully.")


@router.post("/admin/aitool/update")
async def update_ai_tool(
    request: Request,
    id: int = Form(...),
    name: str = Form(...),
    best_for: str = Form(default=""),
    image_url: str = Form(default=""),
    quality_score: float = Form(default=0),
    ease_score: float = Form(default=0),
    accuracy_score: float = Form(default=0),
    speed_score: float = Form(default=0),
    value_score: float = Form(default=0),
    creativity_score: float = Form(default=0),
    integration_score: float = Form(default=0),
    consistency_score: float = Form(default=0),
    support_score: float = Form(default=0),
    time_saved_score: float = Form(default=0),
    display_order: str = Form(default=""),
    is_active: str = Form(default=""),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Updating AI tool ID {id}: {name}")
        payload = {
            "name": name,
            "best_for": best_for,
            "image_url": image_url,
            "quality_score": parse_score(quality_score),
            "ease_score": parse_score(ease_score),
            "accuracy_score": parse_score(accuracy_score),
            "speed_score": parse_score(speed_score),
            "value_score": parse_score(value_score),
            "creativity_score": parse_score(creativity_score),
            "integration_score": parse_score(integration_score),
            "consistency_score": parse_score(consistency_score),
            "support_score": parse_score(support_score),
            "time_saved_score": parse_score(time_saved_score),
            "is_active": parse_checkbox_flag(is_active, default=False),
            "updated_at": datetime.now().isoformat(),
        }
        resolved_display_order = parse_optional_int(display_order)
        if resolved_display_order is not None:
            payload["display_order"] = resolved_display_order

        response = supabase.table("ai_tools").update(payload).eq("id", id).execute()
        print(f"✅ AI tool updated successfully: {response}")
    except Exception as e:
        print(f"❌ Error updating AI tool: {str(e)}")
        traceback.print_exc()
        return admin_redirect("error", "Failed to update AI tool. Check logs and values.")

    return admin_redirect("success", f"AI tool '{name}' updated successfully.")


@router.post("/admin/blog/create")
async def create_blog(
    request: Request,
    title: str = Form(...),
    slug: str = Form(...),
    category: str = Form(...),
    image_url: str = Form(...),
    excerpt: str = Form(...),
    date: str = Form(...),
    html_content: str = Form(default=""),
    is_published: bool = Form(default=False),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Creating blog: {title}")
        now = datetime.now().isoformat()
        payload = {
            "title": title,
            "slug": slug,
            "category": category,
            "image_url": image_url,
            "excerpt": excerpt,
            "date": date,
            "html_content": html_content,
            "created_at": now,
            "update_at": now
        }

        # Try writing with is_published first, fallback to is_publish if column missing
        try:
            payload["is_published"] = is_published
            response = supabase.table("blogs").insert(payload).execute()
        except Exception as e:
            print(f"Create blog: retrying with is_publish due to error: {e}")
            try:
                payload.pop("is_published", None)
                payload["is_publish"] = is_published
                response = supabase.table("blogs").insert(payload).execute()
            except Exception as e2:
                print(f"Create blog failed with alternate key: {e2}")
                raise
        print(f"✅ Blog created successfully: {response}")
    except Exception as e:
        print(f"❌ Error creating blog: {str(e)}")
        traceback.print_exc()
        return admin_redirect("error", "Failed to create blog. Check logs and values.")

    return admin_redirect("success", f"Blog '{title}' created successfully.")


@router.post("/admin/blog/update")
async def update_blog(
    request: Request,
    id: int = Form(...),
    title: str = Form(...),
    slug: str = Form(...),
    category: str = Form(...),
    image_url: str = Form(...),
    excerpt: str = Form(...),
    date: str = Form(...),
    html_content: str = Form(default=""),
    is_published: bool = Form(default=False),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Updating blog ID {id}: {title}")
        now = datetime.now().isoformat()
        payload = {
            "title": title,
            "slug": slug,
            "category": category,
            "image_url": image_url,
            "excerpt": excerpt,
            "date": date,
            "html_content": html_content,
            "update_at": now
        }

        try:
            payload["is_published"] = is_published
            response = supabase.table("blogs").update(payload).eq("id", id).execute()
        except Exception as e:
            print(f"Update blog: retrying with is_publish due to error: {e}")
            try:
                payload.pop("is_published", None)
                payload["is_publish"] = is_published
                response = supabase.table("blogs").update(payload).eq("id", id).execute()
            except Exception as e2:
                print(f"Update blog failed with alternate key: {e2}")
                raise
        print(f"✅ Blog updated successfully: {response}")
    except Exception as e:
        print(f"❌ Error updating blog: {str(e)}")
        traceback.print_exc()
        return admin_redirect("error", "Failed to update blog. Check logs and values.")

    return admin_redirect("success", f"Blog '{title}' updated successfully.")


@router.post("/admin/story/create")
async def create_story(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    img_url: str = Form(...),
    problem: str = Form(...),
    solution: str = Form(...),
    before_text: str = Form(...),
    after_text: str = Form(...),
    cta_text: str = Form(...),
    results: str = Form(default="{}"),
    is_published: str = Form(default=""),
    is_publish: str = Form(default=""),
    auth=Depends(check_auth)
):
    try:
        # Parse results JSON string
        results_data = {}
        if results and results.strip():
            try:
                results_data = json.loads(results)
            except json.JSONDecodeError:
                results_data = {"raw": results}
        
        # determine published flag from either form field
        pub_flag = False
        try:
            if isinstance(is_published, str) and is_published.lower() in ("on", "true", "1"):
                pub_flag = True
            if isinstance(is_publish, str) and is_publish.lower() in ("on", "true", "1"):
                pub_flag = True
        except Exception:
            pub_flag = False

        print(f"🔵 Creating story: {title} (published={pub_flag})")
        now = datetime.now().isoformat()
        payload = {
            "title": title,
            "category": category,
            "img_url": img_url,
            "problem": problem,
            "solution": solution,
            "before_text": before_text,
            "after_text": after_text,
            "cta_text": cta_text,
            "results": results_data,
            "created_at": now,
            "update_at": now
        }
        try:
            payload["is_published"] = pub_flag
            response = supabase.table("stories").insert(payload).execute()
        except Exception as e:
            print(f"Create story: retrying with is_publish due to error: {e}")
            try:
                payload.pop("is_published", None)
                payload["is_publish"] = pub_flag
                response = supabase.table("stories").insert(payload).execute()
            except Exception as e2:
                print(f"Create story failed with alternate key: {e2}")
                raise
        print(f"✅ Story created successfully: {response}")
    except Exception as e:
        print(f"❌ Error creating story: {str(e)}")
        traceback.print_exc()
        return admin_redirect("error", "Failed to create story. Check logs and values.")

    return admin_redirect("success", f"Story '{title}' created successfully.")


@router.post("/admin/story/update")
async def update_story(
    request: Request,
    id: int = Form(...),
    title: str = Form(...),
    category: str = Form(...),
    img_url: str = Form(...),
    problem: str = Form(...),
    solution: str = Form(...),
    before_text: str = Form(...),
    after_text: str = Form(...),
    cta_text: str = Form(...),
    results: str = Form(default="{}"),
    is_published: str = Form(default=""),
    is_publish: str = Form(default=""),
    auth=Depends(check_auth)
):
    try:
        # Parse results JSON string
        results_data = {}
        if results and results.strip():
            try:
                results_data = json.loads(results)
            except json.JSONDecodeError:
                results_data = {"raw": results}
        
        # determine published flag from either form field
        pub_flag = False
        try:
            if isinstance(is_published, str) and is_published.lower() in ("on", "true", "1"):
                pub_flag = True
            if isinstance(is_publish, str) and is_publish.lower() in ("on", "true", "1"):
                pub_flag = True
        except Exception:
            pub_flag = False

        print(f"🔵 Updating story ID {id}: {title} (published={pub_flag})")
        now = datetime.now().isoformat()
        payload = {
            "title": title,
            "category": category,
            "img_url": img_url,
            "problem": problem,
            "solution": solution,
            "before_text": before_text,
            "after_text": after_text,
            "cta_text": cta_text,
            "results": results_data,
            "update_at": now
        }
        try:
            payload["is_published"] = pub_flag
            response = supabase.table("stories").update(payload).eq("id", id).execute()
        except Exception as e:
            print(f"Update story: retrying with is_publish due to error: {e}")
            try:
                payload.pop("is_published", None)
                payload["is_publish"] = pub_flag
                response = supabase.table("stories").update(payload).eq("id", id).execute()
            except Exception as e2:
                print(f"Update story failed with alternate key: {e2}")
                raise
        print(f"✅ Story updated successfully: {response}")
    except Exception as e:
        print(f"❌ Error updating story: {str(e)}")
        traceback.print_exc()
        return admin_redirect("error", "Failed to update story. Check logs and values.")

    return admin_redirect("success", f"Story '{title}' updated successfully.")


@router.get("/admin/logout")
async def admin_logout(request: Request):
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("admin_token")
    return response

