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


@router.get("/admin")
async def admin_root():
    return RedirectResponse(url="/admin/login", status_code=302)


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
    request: Request
):
    try:
        check_auth(request)
    except HTTPException:
        return RedirectResponse(url="/admin/login", status_code=302)

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
        
        # Fetch details for each tool and attach
        for tool in ai_tools:
            try:
                details_res = supabase.table("ai_tool_details").select("*").eq("ai_tool_id", tool["id"]).execute()
                if details_res.data and len(details_res.data) > 0:
                    detail = details_res.data[0]
                    # Parse JSON fields
                    if detail.get("pros"):
                        try:
                            detail["pros"] = json.loads(detail["pros"]) if isinstance(detail["pros"], str) else detail["pros"]
                        except: pass
                    if detail.get("cons"):
                        try:
                            detail["cons"] = json.loads(detail["cons"]) if isinstance(detail["cons"], str) else detail["cons"]
                        except: pass
                    if detail.get("pricing"):
                        try:
                            detail["pricing"] = json.loads(detail["pricing"]) if isinstance(detail["pricing"], str) else detail["pricing"]
                        except: pass
                    tool["details"] = detail
                else:
                    tool["details"] = None
            except:
                tool["details"] = None
    except Exception:
        ai_tools = []
    
    # Fetch use cases with tool names
    try:
        use_cases_data = (
            supabase
            .table("ai_tool_use_cases")
            .select("*, ai_tools(name)")
            .order("id", desc=False)
            .execute()
        )
        use_cases = []
        if use_cases_data.data:
            for uc in use_cases_data.data:
                use_cases.append({
                    "id": uc.get("id"),
                    "ai_tool_id": uc.get("ai_tool_id"),
                    "tool_name": uc.get("ai_tools", {}).get("name", "Unknown") if uc.get("ai_tools") else "Unknown",
                    "title": uc.get("title", ""),
                    "icon": uc.get("icon", ""),
                    "description": uc.get("description", ""),
                    "is_active": uc.get("is_active", True)
                })
    except Exception as e:
        print(f"❌ Error fetching use cases: {str(e)}")
        use_cases = []
    
    # Fetch FAQs with tool names
    try:
        faqs_data = (
            supabase
            .table("ai_tool_faqs")
            .select("*, ai_tools(name)")
            .order("id", desc=False)
            .execute()
        )
        faqs = []
        if faqs_data.data:
            for faq in faqs_data.data:
                faqs.append({
                    "id": faq.get("id"),
                    "ai_tool_id": faq.get("ai_tool_id"),
                    "tool_name": faq.get("ai_tools", {}).get("name", "Unknown") if faq.get("ai_tools") else "Unknown",
                    "question": faq.get("question", ""),
                    "answer": faq.get("answer", ""),
                    "is_active": faq.get("is_active", True)
                })
    except Exception as e:
        print(f"❌ Error fetching FAQs: {str(e)}")
        faqs = []
    
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
            "use_cases": use_cases,
            "faqs": faqs,
            "admin_status": status,
            "admin_message": message,
            **ctx
        }
    )


def admin_redirect(status: str, message: str) -> RedirectResponse:
    query = urlencode({"status": status, "message": message})
    return RedirectResponse(f"/admin/dashboard?{query}", status_code=302)


def admin_json_response(status: str, message: str) -> JSONResponse:
    """Return JSON response for AJAX requests"""
    return JSONResponse({
        "success": status == "success",
        "message": message,
        "status": status,
        "reset_form": status == "success"
    })


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
        return admin_json_response("error", "Failed to create AI tool. Check logs and values.")

    return admin_json_response("success", f"AI tool '{name}' created successfully.")


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
        return admin_json_response("error", "Failed to update AI tool. Check logs and values.")

    return admin_json_response("success", f"AI tool '{name}' updated successfully.")


# ════════════════════════════════════════════════════════════════
# AI TOOLS INFO ROUTES (Details, Use Cases, FAQs)
# ════════════════════════════════════════════════════════════════

@router.post("/admin/aitool/details/save")
async def save_ai_tool_details(
    request: Request,
    ai_tool_id: int = Form(...),
    tagline: str = Form(default=""),
    company: str = Form(default=""),
    founded: str = Form(default=""),
    mmlu_score: str = Form(default=""),
    humaneval_score: str = Form(default=""),
    gsm8k_score: str = Form(default=""),
    hellaswag_score: str = Form(default=""),
    truthfulqa_score: str = Form(default=""),
    headquarters: str = Form(default=""),
    website: str = Form(default=""),
    founders: str = Form(default=""),
    about: str = Form(default=""),
    pros_raw: str = Form(default=""),
    cons_raw: str = Form(default=""),
    pricing_tier: list = Form(default=[]),
    pricing_value: list = Form(default=[]),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Saving details for AI tool ID {ai_tool_id}")
        
        # Parse pros/cons from line-separated text to JSON array
        pros = [line.strip() for line in pros_raw.split('\n') if line.strip()]
        cons = [line.strip() for line in cons_raw.split('\n') if line.strip()]
        
        # Parse pricing tiers
        pricing = []
        for tier, value in zip(pricing_tier, pricing_value):
            if tier.strip() or value.strip():
                pricing.append({"tier": tier.strip(), "value": value.strip()})
        
        payload = {
            "ai_tool_id": ai_tool_id,
            "tagline": tagline,
            "company": company,
            "founded": founded,
            "mmlu_score": mmlu_score,
            "humaneval_score": humaneval_score,
            "gsm8k_score": gsm8k_score,
            "hellaswag_score": hellaswag_score,
            "truthfulqa_score": truthfulqa_score,
            "headquarters": headquarters,
            "website": website,
            "founders": founders,
            "about": about,
            "pros": json.dumps(pros),
            "cons": json.dumps(cons),
            "pricing": json.dumps(pricing),
            "updated_at": datetime.now().isoformat()
        }
        
        # Check if details already exist
        existing = supabase.table("ai_tool_details").select("id").eq("ai_tool_id", ai_tool_id).execute()
        
        if existing.data and len(existing.data) > 0:
            # Update existing
            response = supabase.table("ai_tool_details").update(payload).eq("ai_tool_id", ai_tool_id).execute()
            print(f"✅ AI tool details updated: {response}")
        else:
            # Create new
            payload["created_at"] = datetime.now().isoformat()
            response = supabase.table("ai_tool_details").insert(payload).execute()
            print(f"✅ AI tool details created: {response}")
            
    except Exception as e:
        print(f"❌ Error saving AI tool details: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to save AI tool details. Check logs.")
    
    return admin_json_response("success", "AI tool details saved successfully.")


@router.post("/admin/aitool/usecase/create")
async def create_use_case(
    request: Request,
    ai_tool_id: int = Form(...),
    title: list[str] = Form(...),
    icon: list[str] = Form(default=[]),
    description: list[str] = Form(...),
    is_active: str = Form(default=""),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Creating use cases for AI tool ID {ai_tool_id}")

        # Normalize to list in case of single value submissions
        titles = title if isinstance(title, list) else [title]
        icons = icon if isinstance(icon, list) else [icon]
        descriptions = description if isinstance(description, list) else [description]

        max_len = max(len(titles), len(descriptions))
        payload = []
        for i in range(max_len):
            t = (titles[i] if i < len(titles) else "").strip()
            d = (descriptions[i] if i < len(descriptions) else "").strip()
            ic = (icons[i] if i < len(icons) else "").strip()
            if not t or not d:
                continue
            payload.append({
                "ai_tool_id": ai_tool_id,
                "title": t,
                "icon": ic,
                "description": d,
                "is_active": parse_checkbox_flag(is_active, default=True),
                "created_at": datetime.now().isoformat()
            })

        if not payload:
            return admin_json_response("error", "Please add at least one valid use case row.")

        response = supabase.table("ai_tool_use_cases").insert(payload).execute()
        print(f"✅ Use cases created: {response}")
    except Exception as e:
        print(f"❌ Error creating use case: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", f"Failed to create use case: {str(e)}")

    return admin_json_response("success", f"{len(payload)} use case(s) created successfully.")


@router.post("/admin/aitool/usecase/delete")
async def delete_use_case(
    request: Request,
    id: int = Form(...),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Deleting use case ID {id}")
        response = supabase.table("ai_tool_use_cases").delete().eq("id", id).execute()
        print(f"✅ Use case deleted: {response}")
    except Exception as e:
        print(f"❌ Error deleting use case: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to delete use case. Check logs.")
    
    return admin_json_response("success", "Use case deleted successfully.")


@router.post("/admin/aitool/faq/create")
async def create_faq(
    request: Request,
    ai_tool_id: int = Form(...),
    question: list[str] = Form(...),
    answer: list[str] = Form(...),
    is_active: str = Form(default=""),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Creating FAQs for AI tool ID {ai_tool_id}")

        questions = question if isinstance(question, list) else [question]
        answers = answer if isinstance(answer, list) else [answer]

        max_len = max(len(questions), len(answers))
        payload = []
        for i in range(max_len):
            q = (questions[i] if i < len(questions) else "").strip()
            a = (answers[i] if i < len(answers) else "").strip()
            if not q or not a:
                continue
            payload.append({
                "ai_tool_id": ai_tool_id,
                "question": q,
                "answer": a,
                "is_active": parse_checkbox_flag(is_active, default=True),
                "created_at": datetime.now().isoformat()
            })

        if not payload:
            return admin_json_response("error", "Please add at least one valid FAQ row.")

        response = supabase.table("ai_tool_faqs").insert(payload).execute()
        print(f"✅ FAQs created: {response}")
    except Exception as e:
        print(f"❌ Error creating FAQ: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", f"Failed to create FAQ: {str(e)}")

    return admin_json_response("success", f"{len(payload)} FAQ(s) created successfully.")


@router.post("/admin/aitool/faq/delete")
async def delete_faq(
    request: Request,
    id: int = Form(...),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Deleting FAQ ID {id}")
        response = supabase.table("ai_tool_faqs").delete().eq("id", id).execute()
        print(f"✅ FAQ deleted: {response}")
    except Exception as e:
        print(f"❌ Error deleting FAQ: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to delete FAQ. Check logs.")
    
    return admin_json_response("success", "FAQ deleted successfully.")


@router.post("/admin/aitool/details/update")
async def update_ai_tool_details(
    request: Request,
    ai_tool_id: int = Form(...),
    tagline: str = Form(default=""),
    company: str = Form(default=""),
    founded: str = Form(default=""),
    mmlu_score: str = Form(default=""),
    humaneval_score: str = Form(default=""),
    gsm8k_score: str = Form(default=""),
    hellaswag_score: str = Form(default=""),
    truthfulqa_score: str = Form(default=""),
    headquarters: str = Form(default=""),
    website: str = Form(default=""),
    founders: str = Form(default=""),
    about: str = Form(default=""),
    pros_raw: str = Form(default=""),
    cons_raw: str = Form(default=""),
    pricing_tier: list = Form(default=[]),
    pricing_value: list = Form(default=[]),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Updating details for AI tool ID {ai_tool_id}")
        
        # Parse pros/cons from line-separated text to JSON array
        pros = [line.strip() for line in pros_raw.split('\n') if line.strip()]
        cons = [line.strip() for line in cons_raw.split('\n') if line.strip()]
        
        # Parse pricing tiers
        pricing = []
        for tier, value in zip(pricing_tier, pricing_value):
            if tier.strip() or value.strip():
                pricing.append({"tier": tier.strip(), "value": value.strip()})
        
        payload = {
            "tagline": tagline,
            "company": company,
            "founded": founded,
            "mmlu_score": mmlu_score,
            "humaneval_score": humaneval_score,
            "gsm8k_score": gsm8k_score,
            "hellaswag_score": hellaswag_score,
            "truthfulqa_score": truthfulqa_score,
            "headquarters": headquarters,
            "website": website,
            "founders": founders,
            "about": about,
            "pros": json.dumps(pros),
            "cons": json.dumps(cons),
            "pricing": json.dumps(pricing),
            "updated_at": datetime.now().isoformat()
        }
        
        response = supabase.table("ai_tool_details").update(payload).eq("ai_tool_id", ai_tool_id).execute()
        print(f"✅ AI tool details updated: {response}")
            
    except Exception as e:
        print(f"❌ Error updating AI tool details: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to update AI tool details. Check logs.")
    
    return admin_json_response("success", "AI tool details updated successfully.")


@router.post("/admin/aitool/usecase/update")
async def update_use_case(
    request: Request,
    id: int = Form(...),
    title: str = Form(...),
    icon: str = Form(default=""),
    description: str = Form(...),
    is_active: str = Form(default=""),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Updating use case ID {id}: {title}")
        payload = {
            "title": title,
            "icon": icon,
            "description": description,
            "is_active": parse_checkbox_flag(is_active, default=True),
            "updated_at": datetime.now().isoformat()
        }
        response = supabase.table("ai_tool_use_cases").update(payload).eq("id", id).execute()
        print(f"✅ Use case updated: {response}")
    except Exception as e:
        print(f"❌ Error updating use case: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to update use case. Check logs.")
    
    return admin_json_response("success", f"Use case '{title}' updated successfully.")


@router.post("/admin/aitool/faq/update")
async def update_faq(
    request: Request,
    id: int = Form(...),
    question: str = Form(...),
    answer: str = Form(...),
    is_active: str = Form(default=""),
    auth=Depends(check_auth)
):
    try:
        print(f"🔵 Updating FAQ ID {id}: {question}")
        payload = {
            "question": question,
            "answer": answer,
            "is_active": parse_checkbox_flag(is_active, default=True),
            "updated_at": datetime.now().isoformat()
        }
        response = supabase.table("ai_tool_faqs").update(payload).eq("id", id).execute()
        print(f"✅ FAQ updated: {response}")
    except Exception as e:
        print(f"❌ Error updating FAQ: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to update FAQ. Check logs.")
    
    return admin_json_response("success", "FAQ updated successfully.")


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
        return admin_json_response("error", "Failed to create blog. Check logs and values.")

    return admin_json_response("success", f"Blog '{title}' created successfully.")


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
        return admin_json_response("error", "Failed to update blog. Check logs and values.")

    return admin_json_response("success", f"Blog '{title}' updated successfully.")


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
        return admin_json_response("error", "Failed to create story. Check logs and values.")

    return admin_json_response("success", f"Story '{title}' created successfully.")


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
        return admin_json_response("error", "Failed to update story. Check logs and values.")

    return admin_json_response("success", f"Story '{title}' updated successfully.")


@router.get("/admin/logout")
async def admin_logout(request: Request):
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("admin_token")
    return response

