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
import math
try:
    import resend
except ImportError:
    resend = None
# from jose import JWTError, jwt
# from auth import SECRET_KEY, ALGORITHM


# pricing utilities
from utils.currency import get_price_context, calculate_price

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Add this near the top of pages.py
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SUPABASE_PUBLIC_URL = os.getenv("SUPABASE_PUBLIC_URL", "https://aznlbmkbuwasvaqrnnfo.supabase.co")
SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF6bmxibWtidXdhc3ZhcXJubmZvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE1MDg2MTMsImV4cCI6MjA4NzA4NDYxM30.z_PCB9_JEUeQHGTbJGf7JWJqkF90-kStikh4WNz90MQ",
)

templates.env.globals["base_url"] = BASE_URL
templates.env.globals["supabase_public_url"] = SUPABASE_PUBLIC_URL
templates.env.globals["supabase_anon_key"] = SUPABASE_ANON_KEY

ONE_MONTH_SECONDS = 60 * 60 * 24 * 30
COOKIE_SECURE = BASE_URL.startswith("https://")


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str | None) -> None:
    response.set_cookie(
        "sb-access-token",
        access_token,
        httponly=True,
        max_age=ONE_MONTH_SECONDS,
        path="/",
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    if refresh_token:
        response.set_cookie(
            "sb-refresh-token",
            refresh_token,
            httponly=True,
            max_age=ONE_MONTH_SECONDS,
            path="/",
            samesite="lax",
            secure=COOKIE_SECURE,
        )


def _extract_session_tokens(refresh_result) -> tuple[str | None, str | None, object | None]:
    session_obj = getattr(refresh_result, "session", None)
    user_obj = getattr(refresh_result, "user", None)

    if isinstance(refresh_result, dict):
        session_obj = session_obj or refresh_result.get("session") or refresh_result
        user_obj = user_obj or refresh_result.get("user")

    access_token = None
    refresh_token = None

    if isinstance(session_obj, dict):
        access_token = session_obj.get("access_token")
        refresh_token = session_obj.get("refresh_token")
        user_obj = user_obj or session_obj.get("user")
    elif session_obj is not None:
        access_token = getattr(session_obj, "access_token", None)
        refresh_token = getattr(session_obj, "refresh_token", None)
        user_obj = user_obj or getattr(session_obj, "user", None)

    return access_token, refresh_token, user_obj


def resolve_auth_from_cookies(request: Request) -> dict:
    access_token = request.cookies.get("sb-access-token")
    refresh_token = request.cookies.get("sb-refresh-token")
    user = None
    refreshed = False

    if access_token:
        try:
            auth_user = supabase.auth.get_user(access_token)
            user = auth_user.user if auth_user and auth_user.user else None
        except Exception:
            user = None

    if user:
        return {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "refreshed": False,
        }

    if refresh_token:
        try:
            refresh_result = supabase.auth.refresh_session(refresh_token)
            new_access_token, new_refresh_token, refresh_user = _extract_session_tokens(refresh_result)

            if new_access_token:
                access_token = new_access_token
                refresh_token = new_refresh_token or refresh_token
                refreshed = True

                try:
                    auth_user = supabase.auth.get_user(access_token)
                    user = auth_user.user if auth_user and auth_user.user else None
                except Exception:
                    user = None

                user = user or refresh_user
        except Exception:
            pass

    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "refreshed": refreshed,
    }


def slugify_tool_name(name: str) -> str:
    text = (name or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def infer_tool_icon(name: str) -> str:
    text = (name or "").strip().lower()
    if "claude" in text:
        return "🤖"
    if "chatgpt" in text or "openai" in text:
        return "💬"
    if "gemini" in text:
        return "✨"
    if "copilot" in text:
        return "🐙"
    if "perplexity" in text:
        return "🔍"
    if "canva" in text:
        return "🎨"
    return "🤖"


def _parse_plan_ids(raw_value) -> list:
    if isinstance(raw_value, list):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


async def get_entitlement_state(token: str | None) -> dict:
    """Unified premium entitlement check used across profile, premium page and navbar state."""
    state = {
        "user": None,
        "user_id": None,
        "email": None,
        "plan_ids": [],
        "has_premium": False,
        "premium_expired": False,
        "subscription_state": "free",
    }
    if not token:
        return state

    premium_plan_id = "bdb81597-0b54-4f0e-acea-b88fecf1cb14"

    try:
        auth_user = supabase.auth.get_user(token)
        user = auth_user.user if auth_user and auth_user.user else None
    except Exception:
        user = None

    if not user:
        return state

    user_id = getattr(user, "id", None)
    email = (getattr(user, "email", "") or "").strip().lower()

    state["user"] = user
    state["user_id"] = user_id
    state["email"] = email

    # Admin-granted or manually assigned access via user_profiles.plan_ids.
    if email:
        try:
            plan_res = (
                supabase
                .table("user_profiles")
                .select("plan_ids")
                .eq("email", email)
                .limit(1)
                .execute()
            )
            if plan_res.data:
                state["plan_ids"] = _parse_plan_ids((plan_res.data[0] or {}).get("plan_ids"))
        except Exception:
            state["plan_ids"] = []

    has_admin_premium = premium_plan_id in state["plan_ids"]
    has_paid_premium = False
    premium_expired = False

    # Preferred source: expiry-aware billing view.
    if user_id:
        try:
            billing_res = (
                supabase
                .table("billing_records_effective")
                .select("effective_status,payment_status,expires_at,created_at")
                .eq("user_id", user_id)
                .eq("plan_id", premium_plan_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if billing_res.data:
                row = billing_res.data[0]
                status = str(row.get("effective_status") or row.get("payment_status") or "pending").lower()
                has_paid_premium = status in {"paid", "success", "active"}
                premium_expired = status == "expired"
        except Exception:
            pass

        if not has_paid_premium and not premium_expired and email:
            try:
                billing_res = (
                    supabase
                    .table("billing_records_effective")
                    .select("effective_status,payment_status,expires_at,created_at")
                    .eq("email", email)
                    .eq("plan_id", premium_plan_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if billing_res.data:
                    row = billing_res.data[0]
                    status = str(row.get("effective_status") or row.get("payment_status") or "pending").lower()
                    has_paid_premium = status in {"paid", "success", "active"}
                    premium_expired = status == "expired"
            except Exception:
                pass

    # Legacy fallback: active orders table check.
    if not has_paid_premium and not premium_expired and user_id:
        try:
            order_res = (
                supabase
                .table("orders")
                .select("id")
                .eq("user_id", user_id)
                .eq("plan_id", premium_plan_id)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            has_paid_premium = bool(order_res.data)
        except Exception:
            pass

    state["has_premium"] = has_admin_premium or has_paid_premium
    state["premium_expired"] = premium_expired and not state["has_premium"]
    state["subscription_state"] = "active" if state["has_premium"] else ("expired" if state["premium_expired"] else "free")
    return state


async def ensure_user_profile_exists(token: str | None) -> None:
    """Create a baseline user_profiles row for newly authenticated users."""
    if not token:
        return

    try:
        auth_user = supabase.auth.get_user(token)
        user = auth_user.user if auth_user and auth_user.user else None
    except Exception:
        user = None

    if not user:
        return

    auth_user_id = getattr(user, "id", None)
    email = (getattr(user, "email", "") or "").strip().lower()
    if not email:
        return

    metadata = getattr(user, "user_metadata", {}) or {}
    default_name = (metadata.get("full_name") or metadata.get("name") or "").strip()
    if not default_name:
        default_name = email.split("@")[0]

    free_plan_id = "70e4b369-c45d-48d2-9287-af064a185511"

    try:
        existing_res = (
            supabase
            .table("user_profiles")
            .select("full_name,plan_ids,is_active")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        existing = existing_res.data[0] if existing_res.data else {}
    except Exception:
        existing = {}

    plan_ids = _parse_plan_ids(existing.get("plan_ids"))
    if free_plan_id not in plan_ids:
        plan_ids.append(free_plan_id)

    payload = {
        "auth_user_id": auth_user_id,
        "email": email,
        "full_name": (existing.get("full_name") or default_name),
        "plan_ids": plan_ids,
        "is_active": True if existing.get("is_active") is None else bool(existing.get("is_active")),
    }

    try:
        supabase.table("user_profiles").upsert(payload, on_conflict="email").execute()
    except Exception as e:
        print(f"[AUTH] Unable to ensure user profile for {email}: {e}")

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    route_id = id(request)
    try:
        # print(f"\n🔵 [HOME ROUTE #{route_id}] Starting...")
        
        # print(f"🔵 [HOME ROUTE #{route_id}] Calling get_price_context...")
        ctx = await get_price_context(request)
        # print(f"🔵 [HOME ROUTE #{route_id}] Price context: {ctx}")
        
        featured_ai_tools = []
        top_ai_tool = None

        try:
            tools_res = (
                supabase.table("ai_tools")
                .select(
                    "name,image_url,best_for,"
                    "quality_score,ease_score,accuracy_score,speed_score,value_score,creativity_score,"
                    "integration_score,consistency_score,support_score,time_saved_score"
                )
                .eq("is_active", True)
                .execute()
            )

            def to_float(value):
                try:
                    return float(value)
                except Exception:
                    return 0.0

            def build_tool_payload(tool):
                quality = to_float(tool.get("quality_score"))
                creativity = to_float(tool.get("creativity_score"))
                accuracy = to_float(tool.get("accuracy_score"))
                consistency = to_float(tool.get("consistency_score"))
                speed = to_float(tool.get("speed_score"))
                ease = to_float(tool.get("ease_score"))
                value = to_float(tool.get("value_score"))
                integration = to_float(tool.get("integration_score"))
                support = to_float(tool.get("support_score"))
                time_saved = to_float(tool.get("time_saved_score"))

                all_scores = [
                    quality,
                    ease,
                    accuracy,
                    speed,
                    value,
                    creativity,
                    integration,
                    consistency,
                    support,
                    time_saved,
                ]

                overall = sum(all_scores) / len(all_scores) if all_scores else 0.0

                return {
                    "name": tool.get("name") or "Untitled Tool",
                    "image_url": tool.get("image_url") or "",
                    "best_for": tool.get("best_for") or "General Use",
                    "quality": int(round(quality)),
                    "creativity": int(round(creativity)),
                    "accuracy": int(round(accuracy)),
                    "consistency": int(round(consistency)),
                    "overall": round(overall, 1),
                    "overall_width": max(0, min(100, int(round(overall * 10)))),
                }

            raw_tools = tools_res.data or []
            for tool in raw_tools:
                if isinstance(tool, dict):
                    featured_ai_tools.append(build_tool_payload(tool))

            featured_ai_tools.sort(key=lambda x: x.get("overall", 0), reverse=True)
            if featured_ai_tools:
                top_ai_tool = featured_ai_tools[0]

        except Exception as tools_error:
            print(f"Error loading home AI tools: {tools_error}")

        # print(f"🔵 [HOME ROUTE #{route_id}] Rendering template...")
        response = templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "featured_ai_tools": featured_ai_tools,
                "top_ai_tool": top_ai_tool,
                **ctx,
            },
        )
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
                    "featured_ai_tools": [],
                    "top_ai_tool": None,
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
        # Get currency context
        ctx = await get_price_context(request)
        currency = ctx.get('currency', 'INR')
        
        # Fetch all pricing plans so inactive ones can be shown as Coming Soon.
        plans_response = supabase.table("pricing_plans").select("*").order("display_order").execute()
        
        if plans_response.data:
            plans = []
            for plan in plans_response.data:
                # Convert price based on currency
                price_inr = plan.get('price_inr')
                plan_discount = plan.get('discount_percent', 0)
                if plan.get('is_active') and price_inr is not None and price_inr > 0:
                    from utils.currency import calculate_price
                    # Pass plan-level discount to calculate_price
                    converted_price = await calculate_price(currency, int(price_inr), plan_discount)
                    
                    # Calculate original price if discount exists
                    if plan_discount > 0:
                        original_converted = await calculate_price(currency, int(price_inr / (1 - plan_discount / 100)), 0)
                        plan['original_price_display'] = original_converted
                    else:
                        plan['original_price_display'] = None
                    
                    plan['price_display'] = converted_price
                else:
                    plan['price_display'] = None
                    plan['original_price_display'] = None
                
                plans.append(plan)
            
            ctx['plans'] = plans
        else:
            ctx['plans'] = []
        
        return templates.TemplateResponse("products.html", {"request": request, **ctx})
    except Exception as e:
        print(f"Error in products route: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("products.html", {"request": request, "currency": "INR", "price": 4999, "adv_price": 14999, "symbol": "₹", "plans": []})


@router.get("/product-detail", response_class=HTMLResponse)
async def product_detail(request: Request):
    # Placeholder route for paid product details flow.
    # Keeping this route live prevents broken links while detailed page is prepared.
    return RedirectResponse(url="/products#plans", status_code=302)


@router.get("/premium", response_class=HTMLResponse)
async def premium_page(request: Request):
    ctx = await get_price_context(request)
    currency = ctx.get("currency", "INR")

    premium_plan_id = "bdb81597-0b54-4f0e-acea-b88fecf1cb14"
    premium_price = 99
    premium_original_price = None
    premium_discount_percent = 0
    premium_plan_name = "Premium Workflow Vault"

    auth_state = resolve_auth_from_cookies(request)
    entitlement = await get_entitlement_state(auth_state.get("access_token"))
    has_premium = entitlement.get("has_premium", False)

    # ── If premium user, fetch AI tools for dropdown and show content page ──
    if has_premium:
        ai_tools_dropdown = []
        compare_tools_data = {}
        premium_tabs = [
            {"key": "youtube", "label": "YouTube Creator", "icon": "🎬", "color": "#ef4444"},
            {"key": "instagram", "label": "Instagram Content", "icon": "📸", "color": "#ec4899"},
            {"key": "analyst", "label": "Data Analyst", "icon": "📊", "color": "#6366f1"},
        ]
        premium_tools = []
        try:
            tools_res = (
                supabase.table("ai_tools")
                .select("id, name, image_url, best_for, quality_score, ease_score, accuracy_score, speed_score, value_score, creativity_score, integration_score, consistency_score, support_score, time_saved_score")
                .order("display_order", desc=False)
                .execute()
            )
            def _safe_float(v):
                try: return float(v)
                except: return 0.0

            for t in (tools_res.data or []):
                tool_name = t.get("name") or "Untitled"
                tool_slug = slugify_tool_name(tool_name)
                scores = [
                    _safe_float(t.get("quality_score")), _safe_float(t.get("ease_score")),
                    _safe_float(t.get("accuracy_score")), _safe_float(t.get("speed_score")),
                    _safe_float(t.get("value_score")), _safe_float(t.get("creativity_score")),
                    _safe_float(t.get("integration_score")), _safe_float(t.get("consistency_score")),
                    _safe_float(t.get("support_score")), _safe_float(t.get("time_saved_score")),
                ]
                overall = round(sum(scores) / len(scores), 1) if scores else 0.0
                ai_tools_dropdown.append({
                    "id": t.get("id"),
                    "name": tool_name,
                    "slug": tool_slug,
                    "icon": infer_tool_icon(tool_name),
                    "image_url": t.get("image_url") or "",
                    "best_for": t.get("best_for") or "",
                    "overall": overall,
                })
                compare_tools_data[tool_slug] = {
                    "name": tool_name,
                    "slug": tool_slug,
                    "icon": infer_tool_icon(tool_name),
                    "image_url": t.get("image_url") or "",
                    "tagline": (t.get("best_for") or "Data not updated yet"),
                    "overall": overall,
                    "scores": {
                        "Output Quality": _safe_float(t.get("quality_score")),
                        "Ease of Use": _safe_float(t.get("ease_score")),
                        "Accuracy": _safe_float(t.get("accuracy_score")),
                        "Speed": _safe_float(t.get("speed_score")),
                        "Value for Money": _safe_float(t.get("value_score")),
                        "Creativity": _safe_float(t.get("creativity_score")),
                        "Integration": _safe_float(t.get("integration_score")),
                        "Consistency": _safe_float(t.get("consistency_score")),
                        "Support & Updates": _safe_float(t.get("support_score")),
                        "Time Saved": _safe_float(t.get("time_saved_score")),
                    },
                    "benchmarks": {
                        "MMLU": None,
                        "HumanEval": None,
                        "GSM8K": None,
                        "HellaSwag": None,
                        "TruthfulQA": None,
                    },
                    "details": {
                        "Company": "Data not updated yet",
                        "Founded": "Data not updated yet",
                        "Headquarters": "Data not updated yet",
                        "Website": "Data not updated yet",
                        "Best For": (t.get("best_for") or "Data not updated yet"),
                    },
                    "pros": ["Data not updated yet"],
                    "cons": ["Data not updated yet"],
                    "pricing": [{"name": "Plan", "price": "Data not updated yet", "desc": "Data not updated yet"}],
                    "usecases": [{"icon": "📌", "title": "Use Case", "desc": "Data not updated yet"}],
                }
        except Exception as e:
            print(f"Error loading AI tools for premium content: {e}")

        try:
            workflows_res = (
                supabase.table("premium_workflows")
                .select("id, tool, tab, difficulty, eyebrow_text, eyebrow_color, panel_title, description, stat_pills, tool_chips, result_summary")
                .order("tool")
                .order("tab")
                .execute()
            )
            workflow_rows = workflows_res.data or []
            workflow_ids = [row.get("id") for row in workflow_rows if row.get("id")]

            steps_by_workflow = {}
            results_by_workflow = {}

            if workflow_ids:
                steps_res = (
                    supabase.table("premium_workflow_steps")
                    .select("workflow_id, phase_number, phase_name, step_number, title, tools_used, badge_color, step_num_color, time_estimate, description, prompt, expected_output, pro_tip")
                    .in_("workflow_id", workflow_ids)
                    .order("workflow_id")
                    .order("phase_number")
                    .order("step_number")
                    .execute()
                )
                for row in (steps_res.data or []):
                    steps_by_workflow.setdefault(row.get("workflow_id"), []).append(row)

                results_res = (
                    supabase.table("premium_workflow_results")
                    .select("workflow_id, stat_number, value, label, color")
                    .in_("workflow_id", workflow_ids)
                    .order("workflow_id")
                    .order("stat_number")
                    .execute()
                )
                for row in (results_res.data or []):
                    results_by_workflow.setdefault(row.get("workflow_id"), []).append({
                        "value": row.get("value") or "",
                        "label": row.get("label") or "",
                        "color": row.get("color") or "#ffffff",
                    })

            workflow_lookup = {}
            workflow_name_lookup = {}
            for row in workflow_rows:
                workflow_id = row.get("id")
                tool_name = (row.get("tool") or "Untitled Tool").strip() or "Untitled Tool"
                tool_slug = slugify_tool_name(tool_name)
                tab_key = (row.get("tab") or "").strip().lower()
                phases_map = {}
                for step in steps_by_workflow.get(workflow_id, []):
                    phase_number = step.get("phase_number") or 0
                    if phase_number not in phases_map:
                        phases_map[phase_number] = {
                            "phase_name": step.get("phase_name") or f"Phase {phase_number}",
                            "steps": [],
                        }
                    phases_map[phase_number]["steps"].append({
                        "title": step.get("title") or "",
                        "tools_used": step.get("tools_used") or "",
                        "badge_color": step.get("badge_color") or "",
                        "step_num_color": step.get("step_num_color") or "",
                        "time_estimate": step.get("time_estimate") or "",
                        "description": step.get("description") or "",
                        "prompt": step.get("prompt") or "",
                        "expected_output": step.get("expected_output") or "",
                        "pro_tip": step.get("pro_tip") or "",
                    })

                phases = [phases_map[k] for k in sorted(phases_map.keys())]
                result_summary = results_by_workflow.get(workflow_id) or (row.get("result_summary") or [])
                tool_chips = row.get("tool_chips") or []
                step_count = sum(len(phase.get("steps") or []) for phase in phases)
                workflow_lookup[(tool_slug, tab_key)] = {
                    "id": workflow_id,
                    "tool": tool_name,
                    "tab": tab_key,
                    "difficulty": row.get("difficulty") or "Beginner",
                    "eyebrow_text": row.get("eyebrow_text") or "",
                    "eyebrow_color": row.get("eyebrow_color") or "",
                    "panel_title": row.get("panel_title") or "",
                    "description": row.get("description") or "",
                    "tool_chips": tool_chips,
                    "result_summary": result_summary,
                    "phases": phases,
                    "phase_count": len(phases),
                    "step_count": step_count,
                    "tools_count": len(tool_chips),
                    "estimated_time": (result_summary[0].get("value") if result_summary else ""),
                }
                workflow_name_lookup[tool_slug] = tool_name

            for tool in ai_tools_dropdown:
                tool_tabs = {tab["key"]: workflow_lookup.get((tool["slug"], tab["key"])) for tab in premium_tabs}
                premium_tools.append({
                    **tool,
                    "tabs": tool_tabs,
                })

            existing_slugs = {tool["slug"] for tool in premium_tools}
            extra_slugs = {slug for (slug, _tab) in workflow_lookup.keys() if slug not in existing_slugs}
            for slug in sorted(extra_slugs):
                premium_tools.append({
                    "id": None,
                    "name": workflow_name_lookup.get(slug, slug.replace("-", " ").title()),
                    "slug": slug,
                    "icon": infer_tool_icon(workflow_name_lookup.get(slug, slug)),
                    "image_url": "",
                    "best_for": "",
                    "overall": 0,
                    "tabs": {tab["key"]: workflow_lookup.get((slug, tab["key"])) for tab in premium_tabs},
                })

        except Exception as e:
            print(f"Error loading premium workflow content: {e}")

        initial_premium_tool = premium_tools[0] if premium_tools else {
            "slug": "claude",
            "name": "Claude",
            "icon": "🤖",
        }
        compare_tools = [compare_tools_data[tool["slug"]] for tool in premium_tools if tool.get("slug") in compare_tools_data]
        if not compare_tools:
            compare_tools = [{
                "name": "Claude",
                "slug": "claude",
                "icon": "🤖",
                "image_url": "",
                "tagline": "Data not updated yet",
                "overall": 0,
                "scores": {
                    "Output Quality": 0,
                    "Ease of Use": 0,
                    "Accuracy": 0,
                    "Speed": 0,
                    "Value for Money": 0,
                    "Creativity": 0,
                    "Integration": 0,
                    "Consistency": 0,
                    "Support & Updates": 0,
                    "Time Saved": 0,
                },
                "benchmarks": {"MMLU": None, "HumanEval": None, "GSM8K": None, "HellaSwag": None, "TruthfulQA": None},
                "details": {"Company": "Data not updated yet", "Founded": "Data not updated yet", "Headquarters": "Data not updated yet", "Website": "Data not updated yet", "Best For": "Data not updated yet"},
                "pros": ["Data not updated yet"],
                "cons": ["Data not updated yet"],
                "pricing": [{"name": "Plan", "price": "Data not updated yet", "desc": "Data not updated yet"}],
                "usecases": [{"icon": "📌", "title": "Use Case", "desc": "Data not updated yet"}],
            }]
        compare_default_slugs = [tool.get("slug") for tool in compare_tools[:3] if tool.get("slug")]
        if not compare_default_slugs and compare_tools:
            compare_default_slugs = [compare_tools[0].get("slug")]
        compare_tools_json = {tool.get("slug"): tool for tool in compare_tools if tool.get("slug")}

        response = templates.TemplateResponse(
            "premium_content.html",
            {
                "request": request,
                "ai_tools": ai_tools_dropdown,
                "premium_tools": premium_tools,
                "premium_tabs": premium_tabs,
                "initial_premium_tool_slug": initial_premium_tool.get("slug", "claude"),
                "initial_premium_tool_name": initial_premium_tool.get("name", "Claude"),
                "initial_premium_tool_icon": initial_premium_tool.get("icon", "🤖"),
                "compare_tools": compare_tools,
                "compare_default_slugs": compare_default_slugs,
                "compare_tools_json": json.dumps(compare_tools_json),
                **ctx,
            },
        )
        if auth_state.get("refreshed") and auth_state.get("access_token"):
            _set_auth_cookies(response, auth_state.get("access_token"), auth_state.get("refresh_token"))
        return response

    # ── Non-premium: show pricing/sales page ──
    try:
        plan_res = (
            supabase
            .table("pricing_plans")
            .select("id, plan_name, price_inr, discount_percent")
            .eq("id", premium_plan_id)
            .limit(1)
            .execute()
        )

        if plan_res.data:
            plan = plan_res.data[0]
            base_price_inr = float(plan.get("price_inr") or 99)
            premium_discount_percent = float(plan.get("discount_percent") or 0)
            premium_plan_name = (plan.get("plan_name") or premium_plan_name).strip()

            premium_price = await calculate_price(currency, int(base_price_inr), premium_discount_percent)
            if premium_discount_percent > 0:
                premium_original_price = await calculate_price(currency, int(base_price_inr), 0)
    except Exception as e:
        print(f"Error loading premium plan pricing: {e}")

    preview_tools = []
    try:
        tools_res = (
            supabase.table("ai_tools")
            .select("name")
            .eq("is_active", True)
            .order("display_order", desc=False)
            .execute()
        )
        for row in (tools_res.data or []):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            preview_tools.append({
                "name": name,
                "icon": infer_tool_icon(name),
            })
    except Exception as e:
        print(f"Error loading preview tools for premium page: {e}")

    response = templates.TemplateResponse(
        "premium.html",
        {
            "request": request,
            "premium_plan_id": premium_plan_id,
            "premium_checkout_url": "#",
            "premium_plan_name": premium_plan_name,
            "premium_price": premium_price,
            "premium_original_price": premium_original_price,
            "premium_discount_percent": premium_discount_percent,
            "preview_tools": preview_tools,
            **ctx,
        },
    )
    if auth_state.get("refreshed") and auth_state.get("access_token"):
        _set_auth_cookies(response, auth_state.get("access_token"), auth_state.get("refresh_token"))
    return response


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    ctx = await get_price_context(request)

    auth_state = resolve_auth_from_cookies(request)
    token = auth_state.get("access_token")
    if not token:
        return RedirectResponse(url="/?login=required", status_code=303)

    user = auth_state.get("user")
    if not user:
        return RedirectResponse(url="/?login=required", status_code=303)

    premium_plan_id = "bdb81597-0b54-4f0e-acea-b88fecf1cb14"
    free_plan_id = "70e4b369-c45d-48d2-9287-af064a185511"
    free_plan_default_name = "Budasai Insight"
    email = (user.email or "").strip().lower()
    metadata = user.user_metadata or {}

    full_name = (metadata.get("full_name") or metadata.get("name") or "").strip()
    if not full_name and email:
        full_name = email.split("@")[0]
    if not full_name:
        full_name = "BudasAI User"

    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    profile_row = {}

    entitlement = await get_entitlement_state(token)
    plan_ids = entitlement.get("plan_ids") or []
    has_premium = bool(entitlement.get("has_premium"))
    premium_expired = bool(entitlement.get("premium_expired"))

    # Read profile info from current user_profiles schema first.
    if email:
        try:
            details_res = (
                supabase
                .table("user_profiles")
                .select("full_name,phone_number,dob,profession,created_at")
                .eq("email", email)
                .limit(1)
                .execute()
            )
            if details_res.data:
                profile_row = details_res.data[0] or {}
                db_full_name = str(profile_row.get("full_name") or "").strip()
                if db_full_name:
                    full_name = db_full_name
                    parts = full_name.split()
                    first_name = parts[0] if parts else first_name
                    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        except Exception:
            profile_row = {}

    payment_rows = []

    # Preferred source: billing_records_effective (supports computed expiry and stable history).
    try:
        billing_res = (
            supabase
            .table("billing_records_effective")
            .select("id,plan_id,plan_name,amount,currency,payment_method,transaction_id,created_at,paid_at,expires_at,payment_status,effective_status")
            .eq("user_id", user.id)
            .order("created_at", desc=True)
            .limit(25)
            .execute()
        )

        for row in (billing_res.data or []):
            status = str(row.get("effective_status") or row.get("payment_status") or "pending").lower()
            payment_rows.append(
                {
                    "id": row.get("id"),
                    "plan_id": row.get("plan_id"),
                    "plan_name": row.get("plan_name"),
                    "status": status,
                    "amount": row.get("amount"),
                    "currency": row.get("currency"),
                    "payment_method": row.get("payment_method"),
                    "created_at": row.get("created_at"),
                    "paid_at": row.get("paid_at") or row.get("created_at"),
                    "expires_at": row.get("expires_at"),
                    "transaction_id": row.get("transaction_id"),
                }
            )
    except Exception:
        payment_rows = []

    # Fallback source: orders table (legacy flow).
    if not payment_rows:
        try:
            orders_res = (
                supabase
                .table("orders")
                .select("id,plan_id,status,amount,currency,payment_method,created_at,transaction_id,user_id")
                .eq("user_id", user.id)
                .order("created_at", desc=True)
                .limit(25)
                .execute()
            )
            for row in (orders_res.data or []):
                payment_rows.append(
                    {
                        "id": row.get("id"),
                        "plan_id": row.get("plan_id"),
                        "plan_name": None,
                        "status": str(row.get("status") or "pending").lower(),
                        "amount": row.get("amount"),
                        "currency": row.get("currency"),
                        "payment_method": row.get("payment_method"),
                        "created_at": row.get("created_at"),
                        "paid_at": row.get("created_at"),
                        "expires_at": None,
                        "transaction_id": row.get("transaction_id"),
                    }
                )
        except Exception:
            payment_rows = []

    def _to_dt(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    now_dt = datetime.utcnow()
    premium_payment_statuses = {"paid", "success", "active"}
    latest_paid_premium_dt = None

    for row in payment_rows:
        if str(row.get("plan_id") or "") != premium_plan_id:
            continue
        status = str(row.get("status") or "").lower()
        if status not in premium_payment_statuses:
            continue
        paid_dt = _to_dt(row.get("paid_at") or row.get("created_at"))
        if paid_dt and (latest_paid_premium_dt is None or paid_dt > latest_paid_premium_dt):
            latest_paid_premium_dt = paid_dt

    is_payment_window_active = False
    latest_expiry_dt = None
    for row in payment_rows:
        if str(row.get("plan_id") or "") != premium_plan_id:
            continue
        expiry_dt = _to_dt(row.get("expires_at"))
        if expiry_dt and (latest_expiry_dt is None or expiry_dt > latest_expiry_dt):
            latest_expiry_dt = expiry_dt

    if latest_expiry_dt:
        is_payment_window_active = now_dt < latest_expiry_dt.replace(tzinfo=None)
        premium_expired = not is_payment_window_active
    elif latest_paid_premium_dt:
        # Backward-compatible fallback when expires_at is not available.
        days_active = (now_dt - latest_paid_premium_dt.replace(tzinfo=None)).days
        is_payment_window_active = days_active < 30
        premium_expired = not is_payment_window_active

    # Keep legacy fallback behavior when billing view isn't available.
    if not has_premium and is_payment_window_active:
        has_premium = True

    plan_name_map = {}
    all_plan_ids = list({str(p.get("plan_id")) for p in payment_rows if p.get("plan_id")})
    if premium_plan_id not in all_plan_ids:
        all_plan_ids.append(premium_plan_id)
    if free_plan_id not in all_plan_ids:
        all_plan_ids.append(free_plan_id)
    for pid in plan_ids:
        if pid and pid not in all_plan_ids:
            all_plan_ids.append(pid)

    try:
        if all_plan_ids:
            plans_res = (
                supabase
                .table("pricing_plans")
                .select("id,plan_name,plan_heading,price_inr")
                .in_("id", all_plan_ids)
                .execute()
            )
            for p in plans_res.data or []:
                pid = str(p.get("id") or "")
                if pid:
                    heading = (p.get("plan_heading") or "").strip()
                    plan_name = (p.get("plan_name") or "").strip()
                    plan_name_map[pid] = {
                        "name": heading or plan_name or "BudasAI Plan",
                        "price_inr": p.get("price_inr"),
                    }
    except Exception:
        plan_name_map = {}

    def _format_date(value):
        if not value:
            return "-"
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt.strftime("%d %b %Y")
        except Exception:
            return "-"

    def _format_amount(amount, currency_code):
        if amount is None:
            return "-"
        code = (currency_code or "INR").upper()
        try:
            value = float(amount)
        except Exception:
            return str(amount)
        if code == "INR":
            return f"INR {value:.2f}"
        return f"{code} {value:.2f}"

    status_class_map = {
        "active": "pill-success",
        "paid": "pill-success",
        "success": "pill-success",
        "pending": "pill-pending",
        "failed": "pill-failed",
        "cancelled": "pill-failed",
        "canceled": "pill-failed",
    }

    billing_history = []
    for item in payment_rows:
        status = str(item.get("status") or "pending").lower()
        pid = str(item.get("plan_id") or "")
        plan_info = plan_name_map.get(pid) or {}
        billing_history.append(
            {
                "date": _format_date(item.get("created_at")),
                "plan_name": item.get("plan_name") or plan_info.get("name") or "BudasAI Plan",
                "amount": _format_amount(item.get("amount"), item.get("currency")),
                "method": (item.get("payment_method") or "Online").replace("_", " ").title(),
                "status": status,
                "status_label": status.title(),
                "status_class": status_class_map.get(status, "pill-pending"),
                "txn": item.get("transaction_id") or item.get("id") or "-",
            }
        )

    available_upgrades = []
    owned_plan_ids = {str(pid) for pid in plan_ids if pid}

    try:
        upgrades_res = (
            supabase
            .table("pricing_plans")
            .select("id,plan_name,plan_heading,plan_subheading,price_inr,discount_percent,button_text,is_active,display_order")
            .eq("is_active", True)
            .order("display_order")
            .execute()
        )

        for plan in (upgrades_res.data or []):
            plan_id = str(plan.get("id") or "")
            if not plan_id or plan_id in owned_plan_ids:
                continue

            price_inr = plan.get("price_inr")
            plan_discount = plan.get("discount_percent") or 0
            plan_heading = (plan.get("plan_heading") or plan.get("plan_name") or "BudasAI Plan").strip()
            plan_subheading = (plan.get("plan_subheading") or "Unlock more workflows and premium support.").strip()

            original_price_display = None
            price_display = None
            price_label = "Custom"

            if price_inr is not None:
                try:
                    numeric_price = float(price_inr)
                    if numeric_price == 0:
                        price_label = "Free"
                    elif numeric_price > 0:
                        price_display = await calculate_price(ctx.get("currency", "INR"), int(numeric_price), int(plan_discount))
                        price_label = f"{ctx.get('symbol', '₹')}{price_display}"
                        if plan_discount and 0 < float(plan_discount) < 100:
                            base_original = int(round(numeric_price / (1 - (float(plan_discount) / 100))))
                            original_price_display = await calculate_price(ctx.get("currency", "INR"), base_original, 0)
                except Exception:
                    price_label = "Custom"

            available_upgrades.append(
                {
                    "id": plan_id,
                    "name": plan_heading,
                    "subheading": plan_subheading,
                    "price_label": price_label,
                    "original_price_display": original_price_display,
                    "button_text": (plan.get("button_text") or "Upgrade Now").strip(),
                    "href": f"/plan-action/{plan_id}",
                }
            )
    except Exception:
        available_upgrades = []

    free_plan_name = (plan_name_map.get(free_plan_id) or {}).get("name") or free_plan_default_name
    active_plan_name = free_plan_name
    active_plan_price = "-"
    if has_premium:
        premium_info = plan_name_map.get(premium_plan_id) or {}
        active_plan_name = premium_info.get("name") or "Premium Workflow Vault"
        premium_price_inr = premium_info.get("price_inr")
        if premium_price_inr is not None:
            active_plan_price = _format_amount(premium_price_inr, "INR")

    active_order = next(
        (
            o
            for o in payment_rows
            if str(o.get("status") or "").lower() in {"active", "paid", "success"}
            and str(o.get("plan_id") or "") == premium_plan_id
        ),
        None,
    )
    if active_order:
        pid = str(active_order.get("plan_id") or "")
        active_plan_name = (plan_name_map.get(pid) or {}).get("name") or active_plan_name
        active_plan_price = _format_amount(active_order.get("amount"), active_order.get("currency"))

    if not has_premium:
        active_plan_name = free_plan_name
        active_plan_price = "-"

    member_since = _format_date(getattr(user, "created_at", None))
    if member_since == "-" and profile_row.get("created_at"):
        member_since = _format_date(profile_row.get("created_at"))

    dob_value = profile_row.get("dob") or ""
    if dob_value:
        dob_value = str(dob_value).split("T")[0]

    subscription_state = entitlement.get("subscription_state") or ("active" if has_premium else ("expired" if premium_expired else "free"))

    profile_payload = {
        "full_name": f"{first_name} {last_name}".strip() or full_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": user.email or "-",
        "phone": profile_row.get("phone_number") or "",
        "date_of_birth": dob_value,
        "role": profile_row.get("profession") or "Data Analyst",
        "initial": (first_name[:1] if first_name else full_name[:1]).upper(),
        "member_since": member_since,
        "has_premium": has_premium,
        "subscription_state": subscription_state,
        "active_plan_name": active_plan_name,
        "active_plan_price": active_plan_price,
        "billing_history": billing_history,
    }

    response = templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "profile": profile_payload,
            "available_upgrades": available_upgrades,
            **ctx,
        },
    )
    if auth_state.get("refreshed") and auth_state.get("access_token"):
        _set_auth_cookies(response, auth_state.get("access_token"), auth_state.get("refresh_token"))
    return response


@router.post("/profile/update")
async def profile_update(request: Request):
    auth_state = resolve_auth_from_cookies(request)
    token = auth_state.get("access_token")
    if not token:
        return JSONResponse({"success": False, "message": "Login required"}, status_code=401)

    user = auth_state.get("user")

    if not user or not user.email:
        return JSONResponse({"success": False, "message": "Login required"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "Invalid payload"}, status_code=400)

    first_name = str(body.get("first_name") or "").strip()
    last_name = str(body.get("last_name") or "").strip()
    phone = str(body.get("phone") or "").strip()
    date_of_birth = str(body.get("date_of_birth") or "").strip()
    role = str(body.get("role") or "").strip()

    if not first_name:
        return JSONResponse({"success": False, "message": "First name is required"}, status_code=400)

    if date_of_birth and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_of_birth):
        return JSONResponse({"success": False, "message": "DOB must be YYYY-MM-DD"}, status_code=400)

    email = user.email.strip().lower()
    auth_user_id = getattr(user, "id", None)
    full_name = f"{first_name} {last_name}".strip()
    row = {
        "auth_user_id": auth_user_id,
        "email": email,
        "full_name": full_name,
        "phone_number": phone,
        "dob": date_of_birth or None,
        "profession": role,
    }

    try:
        # Upsert is preferred so first-time users can create their profile row.
        supabase.table("user_profiles").upsert(row, on_conflict="email").execute()
    except Exception:
        try:
            supabase.table("user_profiles").update(row).eq("email", email).execute()
        except Exception as e:
            return JSONResponse({"success": False, "message": f"Unable to update profile: {e}"}, status_code=500)

    response = JSONResponse(
        {
            "success": True,
            "message": "Profile updated",
            "profile": {
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "date_of_birth": date_of_birth,
                "role": role,
            },
        }
    )
    if auth_state.get("refreshed") and auth_state.get("access_token"):
        _set_auth_cookies(response, auth_state.get("access_token"), auth_state.get("refresh_token"))
    return response


@router.post("/profile/delete-account")
async def profile_delete_account(request: Request):
    auth_state = resolve_auth_from_cookies(request)
    token = auth_state.get("access_token")
    if not token:
        return JSONResponse({"success": False, "message": "Login required"}, status_code=401)

    user = auth_state.get("user")

    if not user or not user.email:
        return JSONResponse({"success": False, "message": "Login required"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    confirm_text = str(body.get("confirm_text") or "").strip()
    required_text = "I want to delete my account"
    if confirm_text != required_text:
        return JSONResponse(
            {"success": False, "message": f'Type exactly: "{required_text}"'},
            status_code=400,
        )

    try:
        email = user.email.strip().lower()
        supabase.table("user_profiles").delete().eq("email", email).execute()
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Unable to delete profile: {e}"}, status_code=500)

    # Best-effort cleanup for associated billing rows.
    try:
        supabase.table("billing_records").delete().eq("user_id", user.id).execute()
    except Exception:
        pass

    try:
        supabase.table("orders").delete().eq("user_id", user.id).execute()
    except Exception:
        pass

    response = JSONResponse({"success": True, "message": "Account data deleted"})
    response.delete_cookie("sb-access-token", path="/")
    response.delete_cookie("sb-refresh-token", path="/")
    return response


@router.get("/plan-action/{plan_id}")
async def plan_action(request: Request, plan_id: str):
    auth_state = resolve_auth_from_cookies(request)
    token = auth_state.get("access_token")
    if not token:
        return RedirectResponse(url="/products?login=required", status_code=303)

    user = auth_state.get("user")
    if not user:
        return RedirectResponse(url="/products?login=required", status_code=303)

    try:
        plan_res = (
            supabase
            .table("pricing_plans")
            .select("id, price_inr, button_url, is_active")
            .eq("id", plan_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        plan = plan_res.data[0] if plan_res.data else None
        if not plan:
            return RedirectResponse(url="/products", status_code=303)

        target_url = (plan.get("button_url") or "/products").strip()
        if target_url == "/download-guide":
            response = RedirectResponse(url="/download-guide", status_code=303)
            if auth_state.get("refreshed") and auth_state.get("access_token"):
                _set_auth_cookies(response, auth_state.get("access_token"), auth_state.get("refresh_token"))
            return response
        response = RedirectResponse(url=target_url, status_code=303)
        if auth_state.get("refreshed") and auth_state.get("access_token"):
            _set_auth_cookies(response, auth_state.get("access_token"), auth_state.get("refresh_token"))
        return response
    except Exception as e:
        print(f"Error in /plan-action/{plan_id}: {e}")
        return RedirectResponse(url="/products", status_code=303)


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
        
        # Get count of AI tools
        tools_response = supabase.table("ai_tools").select("id", count="exact").execute()
        ai_tools_count = tools_response.count if tools_response.count else 0
        
        return templates.TemplateResponse("about.html", {"request": request, **ctx, "ai_tools_count": ai_tools_count})
    except Exception as e:
        print(f"Error in about route: {e}")
        return templates.TemplateResponse("about.html", {"request": request, "currency": "INR", "price": 4999, "adv_price": 14999, "symbol": "₹", "ai_tools_count": 0})



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
    auth_state = resolve_auth_from_cookies(request)
    if not auth_state.get("user"):
        return RedirectResponse(url="/products?login=required", status_code=303)

    try:
        # Read filename from site_settings so admin can change it without redeploy
        pdf_filename = "BudasAI Insight Feb 2026.pdf"  # fallback
        try:
            settings_res = supabase.table("site_settings").select("value").eq("key", "free_pdf_filename").limit(1).execute()
            if settings_res.data:
                pdf_filename = settings_res.data[0]["value"]
        except Exception:
            pass  # use fallback filename

        res = supabase.storage.from_("PDFs").create_signed_url(pdf_filename, 60)
        response = RedirectResponse(url=res["signedURL"], status_code=303)
        if auth_state.get("refreshed") and auth_state.get("access_token"):
            _set_auth_cookies(response, auth_state.get("access_token"), auth_state.get("refresh_token"))
        return response
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


@router.get("/ai-tools", response_class=HTMLResponse)
async def ai_tools_rating(request: Request):
    ai_tools = []

    try:
        tools_res = (
            supabase.table("ai_tools")
            .select(
                "name,image_url,best_for,"
                "quality_score,ease_score,accuracy_score,speed_score,value_score,creativity_score,"
                "integration_score,consistency_score,support_score,time_saved_score,display_order"
            )
            .eq("is_active", True)
            .order("display_order", desc=False)
            .execute()
        )

        def to_score(value):
            try:
                return int(float(value))
            except Exception:
                return 0

        tool_rows = tools_res.data or []
        for t in tool_rows:
            ai_tools.append(
                {
                    "name": t.get("name", "Untitled Tool"),
                    "image_url": t.get("image_url", ""),
                    "quality": to_score(t.get("quality_score")),
                    "ease": to_score(t.get("ease_score")),
                    "accuracy": to_score(t.get("accuracy_score")),
                    "speed": to_score(t.get("speed_score")),
                    "value": to_score(t.get("value_score")),
                    "creativity": to_score(t.get("creativity_score")),
                    "integration": to_score(t.get("integration_score")),
                    "consistency": to_score(t.get("consistency_score")),
                    "support": to_score(t.get("support_score")),
                    "time_saved": to_score(t.get("time_saved_score")),
                    "best": t.get("best_for", "General Use"),
                }
            )

    except Exception as e:
        print(f"Error loading AI tools data: {e}")

    return templates.TemplateResponse(
        "ai_tools_rating.html",
        {
            "request": request,
            "ai_tools": ai_tools,
        }
    )


@router.get("/ai-tool-{tool_slug}", response_class=HTMLResponse)
async def ai_tool_detail(request: Request, tool_slug: str):
    try:
        tools_res = (
            supabase.table("ai_tools")
            .select(
                "id,name,image_url,best_for,"
                "quality_score,ease_score,accuracy_score,speed_score,value_score,creativity_score,"
                "integration_score,consistency_score,support_score,time_saved_score"
            )
            .eq("is_active", True)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unable to load AI tools: {e}")

    rows = tools_res.data or []
    tool = None
    for row in rows:
        if slugify_tool_name(row.get("name", "")) == tool_slug:
            tool = row
            break

    if not tool:
        raise HTTPException(status_code=404, detail="AI tool not found")

    def to_float(value):
        try:
            return float(value)
        except Exception:
            return 0.0

    scores = {
        "Output Quality": to_float(tool.get("quality_score")),
        "Ease of Use": to_float(tool.get("ease_score")),
        "Accuracy": to_float(tool.get("accuracy_score")),
        "Speed": to_float(tool.get("speed_score")),
        "Value for Money": to_float(tool.get("value_score")),
        "Creativity": to_float(tool.get("creativity_score")),
        "Integration": to_float(tool.get("integration_score")),
        "Consistency": to_float(tool.get("consistency_score")),
        "Support & Updates": to_float(tool.get("support_score")),
        "Time Saved": to_float(tool.get("time_saved_score")),
    }

    overall = round(sum(scores.values()) / len(scores), 1) if scores else 0.0

    stars_count = max(1, min(5, round(overall / 2)))
    stars_text = "★" * stars_count + "☆" * (5 - stars_count)

    if overall >= 8.5:
        verdict_text = "Excellent - highly recommended"
    elif overall >= 7.0:
        verdict_text = "Very good - recommended"
    elif overall >= 5.5:
        verdict_text = "Average - use with clear purpose"
    else:
        verdict_text = "Below average - evaluate alternatives"

    detail = {
        "tagline": "A practical AI tool reviewed across 10 business-focused criteria.",
        "company": "Not added yet",
        "founded": "Not added yet",
        "accuracy_rate_mmlu": "0%",
        "mmlu_score": 0,
        "humaneval_score": 0,
        "gsm8k_score": 0,
        "hellaswag_score": 0,
        "truthfulqa_score": 0,
        "headquarters": "Not added yet",
        "website": "",
        "founders": "Not added yet",
        "about": f"{tool.get('name', 'This AI tool')} is currently listed on BUDASAI. Detailed product research notes will be added soon.",
        "pros": [
            "Strong overall performance in our baseline scoring model",
            "Useful for practical day-to-day workflows",
            "Can save team time when used with a clear process",
        ],
        "cons": [
            "Detailed pros and cons are not added yet",
            "Advanced workflow notes are pending",
            "Pricing and integration specifics are being prepared",
        ],
        "pricing": [
            {"tier": "Free Plan", "value": "Not added yet"},
            {"tier": "Paid Plan", "value": "Not added yet"},
        ],
        "use_cases": [
            {"title": "Content Drafting", "desc": "Use this tool to create first-draft content quickly."},
            {"title": "Research Support", "desc": "Summarize inputs and gather structured ideas faster."},
            {"title": "Workflow Automation", "desc": "Combine with no-code tools to automate repeat tasks."},
        ],
        "faqs": [
            {
                "q": "Is this tool suitable for beginners?",
                "a": "Usually yes for core use cases. Start with simple prompts and build templates gradually.",
            },
            {
                "q": "How should I evaluate this tool for my business?",
                "a": "Run your top 3 recurring tasks for one week and compare time, quality, and consistency.",
            },
        ],
    }

    try:
        detail_res = (
            supabase.table("ai_tool_details")
            .select("*")
            .eq("ai_tool_id", tool.get("id"))
            .limit(1)
            .execute()
        )
        detail_row = (detail_res.data or [None])[0]
        if isinstance(detail_row, dict):
            detail["tagline"] = detail_row.get("tagline") or detail["tagline"]
            detail["company"] = detail_row.get("company") or detail["company"]
            detail["founded"] = detail_row.get("founded") or detail["founded"]
            detail["mmlu_score"] = detail_row.get("mmlu_score") if detail_row.get("mmlu_score") is not None else detail["mmlu_score"]
            detail["humaneval_score"] = detail_row.get("humaneval_score") if detail_row.get("humaneval_score") is not None else detail["humaneval_score"]
            detail["gsm8k_score"] = detail_row.get("gsm8k_score") if detail_row.get("gsm8k_score") is not None else detail["gsm8k_score"]
            detail["hellaswag_score"] = detail_row.get("hellaswag_score") if detail_row.get("hellaswag_score") is not None else detail["hellaswag_score"]
            detail["truthfulqa_score"] = detail_row.get("truthfulqa_score") if detail_row.get("truthfulqa_score") is not None else detail["truthfulqa_score"]
            detail["headquarters"] = detail_row.get("headquarters") or detail["headquarters"]
            detail["website"] = detail_row.get("website") or detail["website"]
            detail["founders"] = detail_row.get("founders") or detail["founders"]
            detail["about"] = detail_row.get("about") or detail["about"]

            if isinstance(detail_row.get("pros"), list) and detail_row.get("pros"):
                detail["pros"] = detail_row.get("pros")
            if isinstance(detail_row.get("cons"), list) and detail_row.get("cons"):
                detail["cons"] = detail_row.get("cons")
            
            # Handle pricing - could be list or JSON string
            pricing_data = detail_row.get("pricing")
            if pricing_data:
                if isinstance(pricing_data, list):
                    detail["pricing"] = pricing_data
                elif isinstance(pricing_data, str):
                    try:
                        parsed = json.loads(pricing_data)
                        if isinstance(parsed, list):
                            detail["pricing"] = parsed
                    except:
                        pass
            
            if isinstance(detail_row.get("use_cases"), list) and detail_row.get("use_cases"):
                detail["use_cases"] = detail_row.get("use_cases")
            if isinstance(detail_row.get("faqs"), list) and detail_row.get("faqs"):
                detail["faqs"] = detail_row.get("faqs")
    except Exception:
        # Detail table may not exist yet; fall back to defaults.
        pass

    def benchmark_class(score: float) -> str:
        if score >= 8.5:
            return "bm-ex"
        if score >= 7.5:
            return "bm-good"
        if score >= 6.5:
            return "bm-avg"
        if score >= 5.0:
            return "bm-below"
        return "bm-poor"

    benchmarks = [
        {"name": "MMLU", "desc": "Overall Intelligence", "score": to_float(detail.get("mmlu_score"))},
        {"name": "HumanEval", "desc": "Coding Ability", "score": to_float(detail.get("humaneval_score"))},
        {"name": "GSM8K", "desc": "Reasoning & Math", "score": to_float(detail.get("gsm8k_score"))},
        {"name": "HellaSwag", "desc": "Common Sense", "score": to_float(detail.get("hellaswag_score"))},
        {"name": "TruthfulQA", "desc": "Hallucination Control", "score": to_float(detail.get("truthfulqa_score"))},
    ]
    for item in benchmarks:
        item["class"] = benchmark_class(item["score"])

    benchmark_avg = round(sum(item["score"] for item in benchmarks) / len(benchmarks), 1) if benchmarks else 0.0
    benchmark_stars_count = max(1, min(5, round(benchmark_avg / 2)))
    benchmark_stars = "★" * benchmark_stars_count + "☆" * (5 - benchmark_stars_count)

    if benchmark_avg >= 8.5:
        benchmark_verdict = "Excellent across all benchmarks"
    elif benchmark_avg >= 7.0:
        benchmark_verdict = "Strong benchmark performance"
    elif benchmark_avg >= 5.5:
        benchmark_verdict = "Average benchmark performance"
    else:
        benchmark_verdict = "Below average benchmark performance"

    detail["benchmarks"] = benchmarks
    detail["accuracy_rate_mmlu"] = f"{round(to_float(detail.get('mmlu_score')) * 10, 1)}%"
    detail["benchmark_avg"] = benchmark_avg
    detail["benchmark_stars"] = benchmark_stars
    detail["benchmark_verdict"] = benchmark_verdict

    try:
        use_cases_res = (
            supabase.table("ai_tool_use_cases")
            .select("title,icon,description")
            .eq("ai_tool_id", tool.get("id"))
            .order("id", desc=False)
            .execute()
        )
        uc_rows = use_cases_res.data or []
        if uc_rows:
            detail["use_cases"] = [
                {
                    "title": row.get("title") or "Use Case",
                    "icon": row.get("icon") or "",
                    "desc": row.get("description") or "",
                }
                for row in uc_rows
                if isinstance(row, dict)
            ]
    except Exception:
        # Table may not exist yet; keep fallback/use JSON detail values.
        pass

    try:
        faq_res = (
            supabase.table("ai_tool_faqs")
            .select("question,answer")
            .eq("ai_tool_id", tool.get("id"))
            .order("id", desc=False)
            .execute()
        )
        faq_rows = faq_res.data or []
        if faq_rows:
            detail["faqs"] = [
                {
                    "q": row.get("question") or "FAQ",
                    "a": row.get("answer") or "",
                }
                for row in faq_rows
                if isinstance(row, dict)
            ]
    except Exception:
        # Table may not exist yet; keep fallback/use JSON detail values.
        pass

    return templates.TemplateResponse(
        "ai_tool_detail.html",
        {
            "request": request,
            "tool": tool,
            "tool_slug": tool_slug,
            "scores": scores,
            "overall": overall,
            "stars_text": stars_text,
            "verdict_text": verdict_text,
            "detail": detail,
        },
    )


@router.get("/blog", response_class=HTMLResponse)
async def blog(request: Request, page: int = 1, category: str = "all"):
    try:
        PER_PAGE = 4

        # ===== DATABASE QUERY =====
        # Build base query with ordering
        query = supabase.table("blogs").select("*").order("date", desc=True)

        # Execute database query
        response = query.execute()
        blogs_data = response.data or []
        
        print(f"[DEBUG] Total blogs fetched: {len(blogs_data)}")
        if blogs_data:
            print(f"[DEBUG] First blog keys: {blogs_data[0].keys()}")
            print(f"[DEBUG] First blog is_published: {blogs_data[0].get('is_published')}")

        # ===== DATA PROCESSING & FILTERING =====
        # Process blog data and filter by published status and category
        processed_blogs = []
        category_lower = category.lower() if category != "all" else "all"
        
        for blog in blogs_data:
            if not isinstance(blog, dict):
                print(f"[DEBUG] Skipping non-dict: {type(blog)}")
                continue

            # Check if blog is published (handles both field name variations)
            is_pub = blog.get("is_published") or blog.get("is_publish")
            
            if not is_pub:
                print(f"[DEBUG] Skipping unpublished blog: {blog.get('title')} (is_published={blog.get('is_published')}, is_publish={blog.get('is_publish')})")
                continue

            # Filter by category if specified (case-insensitive)
            blog_category = str(blog.get("category", "")).lower()
            if category_lower != "all" and blog_category != category_lower:
                print(f"[DEBUG] Skipping category mismatch: {blog.get('title')} ({blog_category} != {category_lower})")
                continue

            print(f"[DEBUG] Including blog: {blog.get('title')}")

            # Ensure all required fields exist
            blog.setdefault("image_url", "")
            blog.setdefault("excerpt", "")
            blog.setdefault("date", "")
            blog.setdefault("slug", "")

            # Format date to human-readable format
            if blog.get("date"):
                try:
                    dt = datetime.fromisoformat(str(blog["date"]))
                    blog["date"] = dt.strftime("%B %d, %Y")
                except Exception:
                    pass

            # Generate URL-friendly title
            blog["clean_title"] = clean_title_for_url(blog.get("title", ""))

            processed_blogs.append(blog)

        print(f"[DEBUG] Processed blogs after filtering: {len(processed_blogs)}")

        # ===== PAGINATION =====
        # Calculate pagination parameters
        total_blogs = len(processed_blogs)
        total_pages = math.ceil(total_blogs / PER_PAGE) if total_blogs > 0 else 1

        # Validate and constrain page number
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages

        # Slice blogs for current page
        start_idx = (page - 1) * PER_PAGE
        end_idx = start_idx + PER_PAGE
        paginated_blogs = processed_blogs[start_idx:end_idx]

        print(f"[DEBUG] Final paginated blogs: {len(paginated_blogs)}")

        # ===== TEMPLATE RENDERING =====
        # Get price context for display
        ctx = await get_price_context(request)

        return templates.TemplateResponse(
            "blog.html",
            {
                "request": request,
                "blogs": paginated_blogs,
                "page": page,
                "total_pages": total_pages,
                "category": category,
                **ctx
            }
        )

    except Exception as e:
        print(f"[ERROR] in blog route: {e}")  
        import traceback
        traceback.print_exc()

        ctx = await get_price_context(request)
        
        return templates.TemplateResponse(
            "blog.html",
            {
                "request": request,
                "blogs": [],
                "page": 1,
                "total_pages": 1,
                "category": "all",
                **ctx
            }
        )



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
        auth_state = resolve_auth_from_cookies(request)
        token = auth_state.get("access_token")
        if not token:
            return JSONResponse({"user": None, "has_premium": False})
        entitlement = await get_entitlement_state(token)
        user = entitlement.get("user")
        if not user:
            return JSONResponse({"user": None, "has_premium": False})

        response = JSONResponse({"user": user, "has_premium": bool(entitlement.get("has_premium"))})
        if auth_state.get("refreshed") and auth_state.get("access_token"):
            _set_auth_cookies(response, auth_state.get("access_token"), auth_state.get("refresh_token"))
        return response
    except Exception as e:
        print(f"Error in get-user route: {e}")
        return JSONResponse({"user": None, "has_premium": False})


@router.post("/set-auth-token")
async def set_auth_token(request: Request):
    body = await request.json()
    access_token = body.get("accessToken", "")
    refresh_token = body.get("refreshToken", "")

    # Ensure Google/OAuth sign-ins always have a matching user_profiles row.
    await ensure_user_profile_exists(access_token)

    response = JSONResponse({"success": True})
    _set_auth_cookies(response, access_token, refresh_token)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("sb-access-token", path="/")
    response.delete_cookie("sb-refresh-token", path="/")
    return response


RESEND_API_KEY = os.getenv("RESEND_API_KEY")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
SENDER_EMAIL = "bishaldas@budasai.com"


@router.post("/contact")
async def contact(request: Request):
    try:
        form_data = await request.form()

        name = form_data.get("name", "").strip()
        email = form_data.get("email", "").strip().lower()
        business_type = form_data.get("business_type", "").strip()
        message = form_data.get("message", "").strip()

        # Validation
        if not all([name, email, business_type, message]):
            return JSONResponse(
                {"success": False, "message": "All fields are required."},
                status_code=400
            )

        # Rate limiting: Check if this email has submitted in the last 12 hours (twice per day)
        from datetime import timedelta
        cutoff_time = (datetime.now() - timedelta(hours=12)).isoformat()
        
        recent_submission = (
            supabase.table("leads")
            .select("*")
            .eq("email", email)
            .gte("created_at", cutoff_time)
            .execute()
        )

        if recent_submission.data:
            return JSONResponse(
                {"success": False, "message": "You've already submitted a message recently. Please wait 12 hours."},
                status_code=429
            )

        # Get client IP for logging
        client_ip = request.client.host if request.client else "unknown"

        # Save to database
        contact_data = {
            "name": name,
            "email": email,
            "business_type": business_type,
            "message": message,
            "ip_address": client_ip
        }

        result = supabase.table("leads").insert(contact_data).execute()

        if result.data:
            print(f"✅ Contact form saved: {name} ({email})")
            
            # Send email notification to admin
            try:
                if RESEND_API_KEY and ADMIN_EMAIL:
                    resend.api_key = RESEND_API_KEY
                    
                    email_params = {
                        "from": SENDER_EMAIL,
                        "to": [ADMIN_EMAIL],
                        "subject": f"🔔 New Contact Form Submission from {name}",
                        "html": f"""
                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                            <h2 style="color: #2563eb;">New Contact Form Submission</h2>
                            <div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                <p><strong>Name:</strong> {name}</p>
                                <p><strong>Email:</strong> <a href="mailto:{email}">{email}</a></p>
                                <p><strong>Business Type:</strong> {business_type}</p>
                                <p><strong>IP Address:</strong> {client_ip}</p>
                            </div>
                            <div style="background-color: #ffffff; padding: 20px; border-left: 4px solid #2563eb;">
                                <h3 style="margin-top: 0;">Message:</h3>
                                <p style="white-space: pre-wrap;">{message}</p>
                            </div>
                            <p style="color: #6b7280; font-size: 12px; margin-top: 30px;">Sent from BudasAI Contact Form</p>
                        </div>
                        """
                    }
                    
                    resend.Emails.send(email_params)
                    print(f"📧 Admin email notification sent to {ADMIN_EMAIL}")
                    
                    # Send confirmation email to client
                    client_email_params = {
                        "from": SENDER_EMAIL,
                        "to": [email],
                        "subject": "✅ We received your message - BudasAI",
                        "html": f"""
                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                            <div style="text-align: center; margin-bottom: 30px;">
                                <h1 style="color: #2563eb; margin: 0;">BudasAI</h1>
                                <p style="color: #6b7280; margin-top: 5px;">AI Tools Platform</p>
                            </div>
                            
                            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 12px; color: white; text-align: center;">
                                <h2 style="margin: 0; font-size: 28px;">✅ Message Received!</h2>
                                <p style="margin: 10px 0 0 0; opacity: 0.9;">Thank you for reaching out to us</p>
                            </div>
                            
                            <div style="background-color: #f9fafb; padding: 25px; border-radius: 8px; margin: 25px 0;">
                                <p style="margin: 0 0 15px 0; color: #374151;">Hi <strong>{name}</strong>,</p>
                                <p style="margin: 0 0 15px 0; color: #374151; line-height: 1.6;">
                                    We've received your message and our team will review it shortly. 
                                    We typically respond within 24-48 hours during business days.
                                </p>
                            </div>
                            
                            <div style="background-color: #ffffff; padding: 20px; border-left: 4px solid #2563eb; border-radius: 4px;">
                                <h3 style="margin: 0 0 15px 0; color: #1f2937; font-size: 16px;">Your Message Details:</h3>
                                <p style="margin: 5px 0; color: #6b7280;"><strong>Business Type:</strong> {business_type}</p>
                                <p style="margin: 15px 0 5px 0; color: #6b7280;"><strong>Your Message:</strong></p>
                                <p style="margin: 5px 0; color: #374151; padding: 15px; background-color: #f9fafb; border-radius: 6px; white-space: pre-wrap;">{message}</p>
                            </div>
                            
                            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center;">
                                <p style="color: #6b7280; margin: 0 0 10px 0; font-size: 14px;">Follow us on social media:</p>
                                <div style="margin: 15px 0;">
                                    <a href="https://twitter.com/budasai" style="color: #2563eb; text-decoration: none; margin: 0 10px;">Twitter</a>
                                    <a href="https://linkedin.com/company/budasai" style="color: #2563eb; text-decoration: none; margin: 0 10px;">LinkedIn</a>
                                    <a href="https://github.com/budasai" style="color: #2563eb; text-decoration: none; margin: 0 10px;">GitHub</a>
                                </div>
                                <p style="color: #9ca3af; font-size: 12px; margin-top: 20px;">
                                    © 2026 BudasAI. All rights reserved.<br>
                                    This is an automated confirmation email.
                                </p>
                            </div>
                        </div>
                        """
                    }
                    
                    resend.Emails.send(client_email_params)
                    print(f"📧 Confirmation email sent to client: {email}")
                    
                else:
                    print("⚠️  Email notification skipped: RESEND_API_KEY or ADMIN_EMAIL not configured")
            except Exception as email_error:
                # Don't fail the request if email fails
                print(f"❌ Email notification failed: {email_error}")
                import traceback
                traceback.print_exc()
            
            return JSONResponse({"success": True, "message": "Message sent successfully!"})
        else:
            print(f"❌ Contact form save failed: {result}")
            return JSONResponse(
                {"success": False, "message": "Failed to save your message. Please try again."},
                status_code=500
            )

    except Exception as e:
        print(f"❌ Contact form error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"success": False, "message": "An unexpected error occurred. Please try again later."},
            status_code=500
        )



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
