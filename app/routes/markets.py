from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from app.services import data_service as data

router = APIRouter(prefix="/markets")


@router.get("", response_class=HTMLResponse)
def markets(request: Request, region: str = "All", category: str = "All"):
    all_items = data.get_markets()
    regions = data.get_market_regions(all_items)
    selected_region = "All" if region.casefold() == "all" else next((value for value in regions if value.casefold() == region.casefold()), "All")
    items = [market for market in all_items if data.region_matches(market, selected_region)]
    return request.app.state.templates.TemplateResponse(request, "markets.html", {"markets": items, "region": selected_region, "category": category, "regions": regions, "latest_date": data.latest_reference_date(all_items), "seo": {"title": "Markets | BudasAI Research", "description": "Market dashboard powered by BudasAI data."}})


@router.get("/{symbol}", response_class=HTMLResponse)
def detail(request: Request, symbol: str):
    market = data.get_market(symbol)
    if not market:
        raise HTTPException(404, "Market not found")
    return request.app.state.templates.TemplateResponse(request, "market_detail.html", {"market": market, "history": data.get_market_history(symbol), "seo": {"title": f"{market['name']} | BudasAI Research", "description": f"Market data for {market['name']}."}})


@router.get("/{symbol}/history", response_class=JSONResponse)
def history(symbol: str, period: str = "1M"):
    if period.upper() not in {"1W", "1M", "6M", "1Y", "5Y"}:
        raise HTTPException(400, "Unsupported chart period")
    if not data.get_market(symbol):
        raise HTTPException(404, "Market not found")
    return {"period": period.upper(), "points": data.get_market_history(symbol, period)}
