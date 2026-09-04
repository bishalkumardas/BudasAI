from math import ceil

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.services import data_service as data

router = APIRouter(prefix="/daily-news")


@router.get("", response_class=HTMLResponse)
def daily_news(request: Request, page: int = Query(1, ge=1)):
    news, total, error = data.get_daily_news(page=page, per_page=10)
    return request.app.state.templates.TemplateResponse(
        request,
        "daily_news.html",
        {
            "news": news,
            "page": page,
            "total_pages": ceil(total / 10) if total else 0,
            "has_previous": page > 1,
            "has_next": page * 10 < total,
            "error": error,
            "seo": {
                "title": "Daily News | BudasAI Research",
                "description": "Latest business and market news from BudasAI.",
            },
        },
    )
