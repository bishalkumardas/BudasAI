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

        details_map = {}
        tool_ids = [tool.get("id") for tool in ai_tools if tool.get("id") is not None]
        if tool_ids:
            details_res = (
                supabase
                .table("ai_tool_details")
                .select("*")
                .in_("ai_tool_id", tool_ids)
                .execute()
            )
            for detail in (details_res.data or []):
                if detail.get("pros"):
                    try:
                        detail["pros"] = json.loads(detail["pros"]) if isinstance(detail["pros"], str) else detail["pros"]
                    except Exception:
                        pass
                if detail.get("cons"):
                    try:
                        detail["cons"] = json.loads(detail["cons"]) if isinstance(detail["cons"], str) else detail["cons"]
                    except Exception:
                        pass
                if detail.get("pricing"):
                    try:
                        detail["pricing"] = json.loads(detail["pricing"]) if isinstance(detail["pricing"], str) else detail["pricing"]
                    except Exception:
                        pass

                ai_tool_id = detail.get("ai_tool_id")
                if ai_tool_id is not None and ai_tool_id not in details_map:
                    details_map[ai_tool_id] = detail

        for tool in ai_tools:
            tool["details"] = details_map.get(tool.get("id"))
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

    try:
        pricing_res = (
            supabase
            .table("pricing_plans")
            .select("*")
            .order("display_order", desc=False)
            .execute()
        )
        pricing_plans = pricing_res.data if pricing_res.data else []
        for plan in pricing_plans:
            plan["features_list_1"] = parse_json_list(plan.get("features_list_1"))
            plan["features_list_2"] = parse_json_list(plan.get("features_list_2"))
        # Only active paid plans for user access assignment (exclude free / null-price / inactive plans)
        paid_plans = [
            p for p in pricing_plans
            if p.get("is_active") and p.get("price_inr") is not None and float(p.get("price_inr") or 0) > 0
        ]
    except Exception as e:
        print(f"❌ Error fetching pricing plans: {str(e)}")
        pricing_plans = []
        paid_plans = []

    try:
        settings_res = supabase.table("site_settings").select("key,value").execute()
        site_settings = {row["key"]: row["value"] for row in (settings_res.data or [])}
    except Exception as e:
        err_text = str(e)
        if "PGRST205" in err_text and "site_settings" in err_text:
            site_settings = {}
        else:
            print(f"❌ Error fetching site settings: {err_text}")
            site_settings = {}
    free_pdf_filename = site_settings.get("free_pdf_filename", "BudasAI Insight Feb 2026.pdf")

    try:
        users_res = (
            supabase
            .table("user_profiles")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        user_profiles = users_res.data if users_res.data else []
        for user in user_profiles:
            user["plan_ids"] = parse_json_list(user.get("plan_ids"))
    except Exception as e:
        print(f"❌ Error fetching user profiles: {str(e)}")
        user_profiles = []

    try:
        billing_res = (
            supabase
            .table("billing_records")
            .select("*")
            .order("created_at", desc=True)
            .limit(150)
            .execute()
        )
        billing_records = billing_res.data if billing_res.data else []
    except Exception as e:
        print(f"❌ Error fetching billing records: {str(e)}")
        billing_records = []
    
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
            "pricing_plans": pricing_plans,
            "paid_plans": paid_plans,
            "user_profiles": user_profiles,
            "billing_records": billing_records,
            "free_pdf_filename": free_pdf_filename,
            "admin_status": status,
            "admin_message": message,
            **ctx
        }
    )


@router.get("/admin/workflows", response_class=HTMLResponse)
async def admin_workflow_builder(request: Request):
    try:
        check_auth(request)
    except HTTPException:
        return RedirectResponse(url="/admin/login", status_code=302)

    return RedirectResponse(url="/admin/dashboard", status_code=302)


@router.post("/admin/workflow/save")
async def save_admin_workflow(request: Request, auth=Depends(check_auth)):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "error": "Invalid JSON payload"})

    tool = (payload.get("tool") or "").strip()
    tab = (payload.get("tab") or "").strip()
    if not tool or not tab:
        return JSONResponse(status_code=400, content={"success": False, "error": "tool and tab are required"})

    try:
        workflow_row = {
            "tool": tool,
            "tab": tab,
            "difficulty": payload.get("difficulty") or "Beginner",
            "eyebrow_text": payload.get("eyebrow_text") or "",
            "eyebrow_color": payload.get("eyebrow_color") or "#ef4444",
            "panel_title": payload.get("panel_title") or "",
            "description": payload.get("description") or "",
            "stat_pills": payload.get("stat_pills") or [],
            "tool_chips": payload.get("tool_chips") or [],
            "result_summary": payload.get("result_summary") or [],
            "updated_at": datetime.now().isoformat(),
        }

        existing = (
            supabase
            .table("premium_workflows")
            .select("id")
            .eq("tool", tool)
            .eq("tab", tab)
            .limit(1)
            .execute()
        )
        existing_rows = existing.data or []

        if existing_rows:
            workflow_id = existing_rows[0]["id"]
            supabase.table("premium_workflows").update(workflow_row).eq("id", workflow_id).execute()
        else:
            inserted = supabase.table("premium_workflows").insert(workflow_row).execute()
            workflow_id = (inserted.data or [{}])[0].get("id")

        if not workflow_id:
            return JSONResponse(status_code=500, content={"success": False, "error": "Unable to create workflow row"})

        supabase.table("premium_workflow_steps").delete().eq("workflow_id", workflow_id).execute()
        supabase.table("premium_workflow_results").delete().eq("workflow_id", workflow_id).execute()

        steps_to_insert = []
        for phase_index, phase in enumerate(payload.get("phases") or [], start=1):
            phase_name = phase.get("phase_name") or f"Phase {phase_index}"
            for step_index, step in enumerate(phase.get("steps") or [], start=1):
                steps_to_insert.append({
                    "workflow_id": workflow_id,
                    "phase_number": phase_index,
                    "phase_name": phase_name,
                    "step_number": step_index,
                    "title": step.get("title") or "",
                    "tools_used": step.get("tools_used") or "",
                    "badge_color": step.get("badge_color") or None,
                    "step_num_color": step.get("step_num_color") or None,
                    "time_estimate": step.get("time_estimate") or "",
                    "description": step.get("description") or "",
                    "prompt": step.get("prompt") or "",
                    "expected_output": step.get("expected_output") or "",
                    "pro_tip": step.get("pro_tip") or "",
                })

        if steps_to_insert:
            supabase.table("premium_workflow_steps").insert(steps_to_insert).execute()

        results_to_insert = []
        for stat_number, stat in enumerate(payload.get("result_summary") or [], start=1):
            results_to_insert.append({
                "workflow_id": workflow_id,
                "stat_number": stat_number,
                "value": stat.get("value") or "",
                "label": stat.get("label") or "",
                "color": stat.get("color") or "#ffffff",
            })
        if results_to_insert:
            supabase.table("premium_workflow_results").insert(results_to_insert).execute()

        return {"success": True, "workflow_id": workflow_id}
    except Exception as e:
        print(f"❌ Error saving admin workflow: {str(e)}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@router.get("/admin/workflow/load")
async def load_admin_workflow(tool: str = "", tab: str = "", auth=Depends(check_auth)):
    tool = (tool or "").strip()
    tab = (tab or "").strip()
    if not tool or not tab:
        return JSONResponse(status_code=400, content={"success": False, "error": "tool and tab are required"})

    try:
        workflow_result = (
            supabase
            .table("premium_workflows")
            .select("*")
            .eq("tool", tool)
            .eq("tab", tab)
            .limit(1)
            .execute()
        )
        workflow_rows = workflow_result.data or []
        if not workflow_rows:
            return {"success": True, "workflow": None}

        workflow = workflow_rows[0]
        workflow_id = workflow["id"]

        steps_result = (
            supabase
            .table("premium_workflow_steps")
            .select("*")
            .eq("workflow_id", workflow_id)
            .order("phase_number")
            .order("step_number")
            .execute()
        )
        steps_rows = steps_result.data or []

        phases_map = {}
        for row in steps_rows:
            phase_number = row.get("phase_number")
            if phase_number not in phases_map:
                phases_map[phase_number] = {
                    "phase_name": row.get("phase_name") or "",
                    "steps": [],
                }
            phases_map[phase_number]["steps"].append({
                "title": row.get("title") or "",
                "tools_used": row.get("tools_used") or "",
                "badge_color": row.get("badge_color") or "",
                "step_num_color": row.get("step_num_color") or "",
                "time_estimate": row.get("time_estimate") or "",
                "description": row.get("description") or "",
                "prompt": row.get("prompt") or "",
                "expected_output": row.get("expected_output") or "",
                "pro_tip": row.get("pro_tip") or "",
            })
        phases = [phases_map[k] for k in sorted(phases_map.keys())]

        results_result = (
            supabase
            .table("premium_workflow_results")
            .select("*")
            .eq("workflow_id", workflow_id)
            .order("stat_number")
            .execute()
        )
        results_rows = results_result.data or []
        result_summary = [
            {
                "value": row.get("value") or "",
                "label": row.get("label") or "",
                "color": row.get("color") or "#ffffff",
            }
            for row in results_rows
        ]

        return {
            "success": True,
            "workflow": {
                "id": workflow_id,
                "tool": workflow.get("tool") or "",
                "tab": workflow.get("tab") or "",
                "difficulty": workflow.get("difficulty") or "Beginner",
                "eyebrow_text": workflow.get("eyebrow_text") or "",
                "eyebrow_color": workflow.get("eyebrow_color") or "#ef4444",
                "panel_title": workflow.get("panel_title") or "",
                "description": workflow.get("description") or "",
                "stat_pills": workflow.get("stat_pills") or [],
                "tool_chips": workflow.get("tool_chips") or [],
                "result_summary": result_summary if result_summary else (workflow.get("result_summary") or []),
                "phases": phases,
            },
        }
    except Exception as e:
        print(f"❌ Error loading admin workflow: {str(e)}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@router.get("/admin/api/pricing-plan/{plan_id}")
async def get_pricing_plan(plan_id: str, auth=Depends(check_auth)):
    try:
        result = (
            supabase
            .table("pricing_plans")
            .select("*")
            .eq("id", plan_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return {"success": len(rows) > 0, "plan": rows[0] if rows else None}
    except Exception as e:
        print(f"❌ Error loading pricing plan {plan_id}: {str(e)}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@router.post("/admin/api/pricing-plan/update")
async def update_pricing_plan(request: Request, auth=Depends(check_auth)):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "error": "Invalid JSON payload"})

    plan_id = payload.get("id")
    if not plan_id:
        return JSONResponse(status_code=400, content={"success": False, "error": "Missing plan id"})

    try:
        update_payload = {
            "plan_name": payload.get("plan_name"),
            "plan_heading": payload.get("plan_heading"),
            "plan_subheading": payload.get("plan_subheading"),
            "price_inr": payload.get("price_inr"),
            "discount_percent": payload.get("discount_percent"),
            "features_heading_1": payload.get("features_heading_1"),
            "features_list_1": payload.get("features_list_1") or [],
            "features_heading_2": payload.get("features_heading_2"),
            "features_list_2": payload.get("features_list_2") or [],
            "button_text": payload.get("button_text"),
            "button_action": payload.get("button_action"),
            "button_url": payload.get("button_url"),
            "show_terms": bool(payload.get("show_terms", False)),
            "is_popular": bool(payload.get("is_popular", False)),
            "display_order": payload.get("display_order"),
            "is_active": bool(payload.get("is_active", False)),
            "card_bg_color": payload.get("card_bg_color"),
            "badge_bg_color": payload.get("badge_bg_color"),
            "badge_text_color": payload.get("badge_text_color"),
            "badge_text": payload.get("badge_text"),
            "price_note": payload.get("price_note"),
            "updated_at": datetime.now().isoformat(),
        }

        result = (
            supabase
            .table("pricing_plans")
            .update(update_payload)
            .eq("id", plan_id)
            .execute()
        )

        return {"success": True, "updated": len(result.data or []), "plan_id": plan_id}
    except Exception as e:
        print(f"❌ Error updating pricing plan {plan_id}: {str(e)}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


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


def parse_json_list(value: str | list | None) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def add_months_iso(start_iso: str, months: int) -> str:
    """Add calendar months to an ISO timestamp and return ISO string."""
    start_dt = datetime.fromisoformat(start_iso)

    year = start_dt.year
    month = start_dt.month + months
    day = start_dt.day

    while month > 12:
        month -= 12
        year += 1

    if month == 2:
        is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
        max_day = 29 if is_leap else 28
    elif month in {4, 6, 9, 11}:
        max_day = 30
    else:
        max_day = 31

    safe_day = min(day, max_day)
    end_dt = start_dt.replace(year=year, month=month, day=safe_day)
    return end_dt.isoformat()


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
            "update_at": now,
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


@router.post("/admin/pricing/create")
async def create_pricing_plan(
    request: Request,
    plan_name: str = Form(...),
    plan_heading: str = Form(...),
    plan_subheading: str = Form(default=""),
    price_inr: str = Form(default=""),
    discount_percent: str = Form(default="0"),
    features_heading_1: str = Form(default=""),
    features_list_1: str = Form(default="[]"),
    features_heading_2: str = Form(default=""),
    features_list_2: str = Form(default="[]"),
    button_text: str = Form(...),
    price_note: str = Form(default=""),
    button_url: str = Form(default="/about#contact-section"),
    custom_button_url: str = Form(default=""),
    show_terms: str = Form(default=""),
    is_popular: str = Form(default=""),
    display_order: str = Form(default="0"),
    is_active: str = Form(default=""),
    card_bg_color: str = Form(default="#ffffff"),
    badge_bg_color: str = Form(default="#3C83F6"),
    badge_text_color: str = Form(default="#ffffff"),
    badge_text: str = Form(default="Standard"),
    auth=Depends(check_auth)
):
    try:
        selected_button_url = button_url.strip()
        if selected_button_url == "__custom__":
            selected_button_url = custom_button_url.strip()
        if not selected_button_url:
            selected_button_url = "/about#contact-section"

        parsed_price = None
        if price_inr.strip() != "":
            parsed_price = float(price_inr)

        payload = {
            "plan_name": plan_name.strip(),
            "plan_heading": plan_heading.strip(),
            "plan_subheading": plan_subheading.strip(),
            "price_inr": parsed_price,
            "discount_percent": float(discount_percent or 0),
            "features_heading_1": features_heading_1.strip(),
            "features_list_1": parse_json_list(features_list_1),
            "features_heading_2": features_heading_2.strip(),
            "features_list_2": parse_json_list(features_list_2),
            "button_text": button_text.strip(),
            "price_note": price_note.strip(),
            "button_url": selected_button_url,
            "show_terms": parse_checkbox_flag(show_terms, default=False),
            "is_popular": parse_checkbox_flag(is_popular, default=False),
            "display_order": int(display_order or 0),
            "is_active": parse_checkbox_flag(is_active, default=False),
            "card_bg_color": card_bg_color.strip() or "#ffffff",
            "badge_bg_color": badge_bg_color.strip() or "#3C83F6",
            "badge_text_color": badge_text_color.strip() or "#ffffff",
            "badge_text": badge_text.strip() or "Standard",
        }

        supabase.table("pricing_plans").insert(payload).execute()
        return admin_json_response("success", f"Pricing plan '{plan_heading}' created successfully.")
    except Exception as e:
        print(f"❌ Error creating pricing plan: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to create pricing plan.")


@router.post("/admin/pricing/update")
async def update_pricing_plan(
    request: Request,
    id: str = Form(...),
    plan_name: str = Form(...),
    plan_heading: str = Form(...),
    plan_subheading: str = Form(default=""),
    price_inr: str = Form(default=""),
    discount_percent: str = Form(default="0"),
    features_heading_1: str = Form(default=""),
    features_list_1: str = Form(default="[]"),
    features_heading_2: str = Form(default=""),
    features_list_2: str = Form(default="[]"),
    button_text: str = Form(...),
    price_note: str = Form(default=""),
    button_url: str = Form(default="/about#contact-section"),
    custom_button_url: str = Form(default=""),
    show_terms: str = Form(default=""),
    is_popular: str = Form(default=""),
    display_order: str = Form(default="0"),
    is_active: str = Form(default=""),
    card_bg_color: str = Form(default="#ffffff"),
    badge_bg_color: str = Form(default="#3C83F6"),
    badge_text_color: str = Form(default="#ffffff"),
    badge_text: str = Form(default="Standard"),
    auth=Depends(check_auth)
):
    try:
        selected_button_url = button_url.strip()
        if selected_button_url == "__custom__":
            selected_button_url = custom_button_url.strip()
        if not selected_button_url:
            selected_button_url = "/about#contact-section"

        parsed_price = None
        if price_inr.strip() != "":
            parsed_price = float(price_inr)

        payload = {
            "plan_name": plan_name.strip(),
            "plan_heading": plan_heading.strip(),
            "plan_subheading": plan_subheading.strip(),
            "price_inr": parsed_price,
            "discount_percent": float(discount_percent or 0),
            "features_heading_1": features_heading_1.strip(),
            "features_list_1": parse_json_list(features_list_1),
            "features_heading_2": features_heading_2.strip(),
            "features_list_2": parse_json_list(features_list_2),
            "button_text": button_text.strip(),
            "price_note": price_note.strip(),
            "button_url": selected_button_url,
            "show_terms": parse_checkbox_flag(show_terms, default=False),
            "is_popular": parse_checkbox_flag(is_popular, default=False),
            "display_order": int(display_order or 0),
            "is_active": parse_checkbox_flag(is_active, default=False),
            "card_bg_color": card_bg_color.strip() or "#ffffff",
            "badge_bg_color": badge_bg_color.strip() or "#3C83F6",
            "badge_text_color": badge_text_color.strip() or "#ffffff",
            "badge_text": badge_text.strip() or "Standard",
            "updated_at": datetime.now().isoformat(),
        }

        supabase.table("pricing_plans").update(payload).eq("id", id).execute()
        return admin_json_response("success", f"Pricing plan '{plan_heading}' updated successfully.")
    except Exception as e:
        print(f"❌ Error updating pricing plan: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to update pricing plan.")


@router.post("/admin/user/create")
async def create_user_profile(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(default=""),
    phone_number: str = Form(default=""),
    dob: str = Form(default=""),
    profession: str = Form(default=""),
    is_active: str = Form(default="on"),
    auth=Depends(check_auth)
):
    try:
        # Ensure free plan is always included for new users.
        FREE_PLAN_ID = "70e4b369-c45d-48d2-9287-af064a185511"
        normalized_plan_ids = [FREE_PLAN_ID]
        
        payload = {
            "email": email.strip().lower(),
            "full_name": full_name.strip(),
            "phone_number": phone_number.strip(),
            "dob": dob.strip() or None,
            "profession": profession.strip(),
            "plan_ids": normalized_plan_ids,
            "is_active": parse_checkbox_flag(is_active, default=True),
        }

        supabase.table("user_profiles").insert(payload).execute()
        return admin_json_response("success", f"User profile created for {payload['email']}.")
    except Exception as e:
        print(f"❌ Error creating user profile: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to create user profile.")


@router.post("/admin/user/update")
async def update_user_profile(
    request: Request,
    id: str = Form(...),
    email: str = Form(...),
    full_name: str = Form(default=""),
    phone_number: str = Form(default=""),
    dob: str = Form(default=""),
    profession: str = Form(default=""),
    is_active: str = Form(default="on"),
    auth=Depends(check_auth)
):
    try:
        # Keep existing plan_ids unchanged here; billing form controls paid activation.
        existing_plan_ids = []
        try:
            existing_user_res = (
                supabase
                .table("user_profiles")
                .select("plan_ids")
                .eq("id", id)
                .limit(1)
                .execute()
            )
            if existing_user_res.data:
                existing_plan_ids = parse_json_list(existing_user_res.data[0].get("plan_ids"))
        except Exception:
            existing_plan_ids = []

        payload = {
            "email": email.strip().lower(),
            "full_name": full_name.strip(),
            "phone_number": phone_number.strip(),
            "dob": dob.strip() or None,
            "profession": profession.strip(),
            "plan_ids": existing_plan_ids,
            "is_active": parse_checkbox_flag(is_active, default=True),
            "updated_at": datetime.now().isoformat(),
        }

        supabase.table("user_profiles").update(payload).eq("id", id).execute()
        return admin_json_response("success", f"User profile updated for {payload['email']}.")
    except Exception as e:
        print(f"❌ Error updating user profile: {str(e)}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to update user profile.")


@router.post("/admin/billing/create")
async def create_billing_record(
    request: Request,
    user_id: str = Form(...),
    plan_id: str = Form(...),
    duration_months: str = Form(...),
    amount: str = Form(default=""),
    currency: str = Form(default="INR"),
    payment_method: str = Form(default="manual"),
    transaction_id: str = Form(default=""),
    payment_status: str = Form(default="paid"),
    auth=Depends(check_auth)
):
    try:
        months = int(duration_months)
        if months not in {1, 3, 6, 12}:
            return admin_json_response("error", "Invalid duration. Use 1, 3, 6 or 12 months.")
    except Exception:
        return admin_json_response("error", "Invalid duration value.")

    try:
        user_res = (
            supabase
            .table("user_profiles")
            .select("id,auth_user_id,email,plan_ids")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if not user_res.data:
            return admin_json_response("error", "User not found.")
        user_row = user_res.data[0]
        user_email = (user_row.get("email") or "").strip().lower()
        billing_user_id = user_row.get("auth_user_id") or user_row.get("id")
        if not user_email:
            return admin_json_response("error", "Selected user does not have a valid email.")
        if not billing_user_id:
            return admin_json_response("error", "Selected user does not have a valid auth user ID.")
    except Exception as e:
        print(f"❌ Error loading user for billing: {str(e)}")
        return admin_json_response("error", "Unable to load selected user.")

    try:
        plan_res = (
            supabase
            .table("pricing_plans")
            .select("id,plan_name,plan_heading,price_inr")
            .eq("id", plan_id)
            .limit(1)
            .execute()
        )
        if not plan_res.data:
            return admin_json_response("error", "Selected plan not found.")
        plan_row = plan_res.data[0]
    except Exception as e:
        print(f"❌ Error loading plan for billing: {str(e)}")
        return admin_json_response("error", "Unable to load selected plan.")

    plan_name = (plan_row.get("plan_heading") or plan_row.get("plan_name") or "BudasAI Plan").strip()
    now_iso = datetime.now().isoformat()
    expires_at = add_months_iso(now_iso, months)

    try:
        amount_value = float(amount) if str(amount).strip() else float(plan_row.get("price_inr") or 0)
    except Exception:
        amount_value = float(plan_row.get("price_inr") or 0)

    currency_code = (currency or "INR").upper()
    status_value = (payment_status or "paid").strip().lower()
    if status_value not in {"paid", "success", "pending", "failed", "refunded", "active"}:
        status_value = "paid"

    billing_payload = {
        "user_id": billing_user_id,
        "email": user_email,
        "plan_id": plan_id,
        "plan_name": plan_name,
        "amount": amount_value,
        "currency": currency_code,
        "payment_method": payment_method.strip(),
        "transaction_id": transaction_id.strip() or None,
        "payment_status": status_value,
        "paid_at": now_iso,
        "starts_at": now_iso,
        "expires_at": expires_at,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    try:
        supabase.table("billing_records").insert(billing_payload).execute()
    except Exception as e:
        print(f"❌ Error creating billing record: {str(e)}")
        return admin_json_response(
            "error",
            "Failed to create billing record. Ensure billing_records table exists with required columns.",
        )

    if status_value in {"paid", "success", "active"}:
        try:
            plan_ids = parse_json_list(user_row.get("plan_ids"))
            if plan_id not in plan_ids:
                plan_ids.append(plan_id)
            supabase.table("user_profiles").update(
                {
                    "plan_ids": plan_ids,
                    "updated_at": datetime.now().isoformat(),
                }
            ).eq("id", user_id).execute()
        except Exception as e:
            print(f"❌ Billing created but failed to update user plan access: {str(e)}")
            return admin_json_response("error", "Billing added but failed to sync user plan access.")

    return admin_json_response("success", f"Billing added: {plan_name} active for {months} month(s).")


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


@router.post("/admin/settings/update")
async def update_site_settings(
    request: Request,
    free_pdf_filename: str = Form(...),
    auth=Depends(check_auth)
):
    try:
        filename = free_pdf_filename.strip()
        if not filename:
            return admin_json_response("error", "PDF filename cannot be empty.")

        supabase.table("site_settings").upsert(
            {"key": "free_pdf_filename", "value": filename},
            on_conflict="key"
        ).execute()
        return admin_json_response("success", f"PDF filename updated to: {filename}")
    except Exception as e:
        err_text = str(e)
        if "PGRST205" in err_text and "site_settings" in err_text:
            return admin_json_response(
                "error",
                "site_settings table is missing in DB. Create it first to use Site Settings."
            )
        print(f"❌ Error updating site settings: {err_text}")
        traceback.print_exc()
        return admin_json_response("error", "Failed to update settings.")

