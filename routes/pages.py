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
# from jose import JWTError, jwt
# from auth import SECRET_KEY, ALGORITHM


# pricing utilities
from utils.currency import get_price_context

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Add this near the top of pages.py
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def slugify_tool_name(name: str) -> str:
    text = (name or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")

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
