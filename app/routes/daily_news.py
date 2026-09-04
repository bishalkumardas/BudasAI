from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.services import data_service as data

router = APIRouter(prefix="/daily-news")


def _pagination_items(page, total_pages):
    if total_pages <= 7:
        return list(range(1, total_pages + 1))

    visible_pages = {1, total_pages, page}
    visible_pages.update(range(max(1, page - 1), min(total_pages, page + 1) + 1))
    if page <= 3:
        visible_pages.update({2, 3})
    if page >= total_pages - 2:
        visible_pages.update({total_pages - 2, total_pages - 1})

    items = []
    previous_page = None
    for page_number in sorted(visible_pages):
        if previous_page is not None and page_number - previous_page > 1:
            items.append(None)
        items.append(page_number)
        previous_page = page_number
    return items


@router.get("", response_class=HTMLResponse)
def daily_news(request: Request, page: int = Query(1, ge=1)):
    news, total, error = data.get_daily_news(page=page, per_page=10)
    total_pages = ceil(total / 10) if total else 0
    if page > (total_pages or 1):
        raise HTTPException(404, "Daily News page not found")
    query_params = [(key, value) for key, value in request.query_params.multi_items() if key != "page"]
    query_string = urlencode(query_params)
    pagination_url = f"/daily-news?{query_string + '&' if query_string else ''}page="
    return request.app.state.templates.TemplateResponse(
        request,
        "daily_news.html",
        {
            "news": news,
            "page": page,
            "total_pages": total_pages,
            "pagination_items": _pagination_items(page, total_pages),
            "pagination_url": pagination_url,
            "has_previous": page > 1,
            "has_next": page * 10 < total,
            "error": error,
            "seo": {
                "title": "Daily News | BudasAI Research",
                "description": "Latest business and market news from BudasAI.",
            },
        },
    )
