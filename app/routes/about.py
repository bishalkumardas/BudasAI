from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
router=APIRouter()
@router.get("/about", response_class=HTMLResponse)
def about(request:Request): return request.app.state.templates.TemplateResponse(request,"about.html",{"seo":{"title":"About | BudasAI Research","description":"About BudasAI Research and its research philosophy."}})
