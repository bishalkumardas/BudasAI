from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routes import about, daily_news, home, markets, research
from app.services import data_service as data
app=FastAPI(title="BudasAI Research")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates=Jinja2Templates(directory="templates")
templates.env.globals.update(get_markets=data.get_markets, search_articles=data.search_articles)
templates.env.filters["format_display_date"] = data.format_display_date
templates.env.filters["format_news_date"] = data.format_news_date
app.state.templates=templates
for route in (home.router, markets.router, research.router, about.router, daily_news.router): app.include_router(route)
@app.get("/search")
def search(request:Request, q:str=""):
    return templates.TemplateResponse(request,"search_results.html",{"results":data.search_site(q),"q":q,"seo":{"title":"Search | BudasAI Research","description":"Search BudasAI Research."}})
