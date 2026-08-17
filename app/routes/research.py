from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from app.services import data_service as data
router=APIRouter(prefix="/research")
@router.get("", response_class=HTMLResponse)
def research(request:Request, category:str="All", page:int=1):
    if page<1: raise HTTPException(404)
    articles,total=data.get_articles(None if category=="All" else category,page)
    return request.app.state.templates.TemplateResponse(request,"research.html",{"articles":articles,"categories":data.get_categories(),"category":category,"page":page,"has_more":page*6<total,"seo":{"title":"Research | BudasAI Research","description":"Financial research and learning notes."}})
@router.get("/{slug}", response_class=HTMLResponse)
def article(request:Request, slug:str):
    item=data.get_article(slug)
    if not item: raise HTTPException(404,"Article not found")
    related=[a for a in data.get_articles_by_category(item["category"]) if a["slug"]!=slug][:3]
    return request.app.state.templates.TemplateResponse(request,"article.html",{"article":item,"related":related,"seo":{"title":item["title"]+" | BudasAI Research","description":item["excerpt"],"type":"article"}})
