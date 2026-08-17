from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.services import data_service as data
router=APIRouter()
@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    articles,_=data.get_articles(); return request.app.state.templates.TemplateResponse(request,"home.html", {"markets":data.get_markets()[:5],"articles":articles,"categories":data.get_categories(),"seo":{"title":"BudasAI Research | Independent Financial Thinking","description":"Independent research on equity, fixed income, markets and CFA concepts."}})
