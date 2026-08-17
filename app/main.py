from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routes import home, markets, research, about
from app.services import data_service as data
app=FastAPI(title="BudasAI Research")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates=Jinja2Templates(directory="templates")
templates.env.globals.update(get_markets=lambda: data.get_markets()[:8], search_articles=data.search_articles)
app.state.templates=templates
for route in (home.router, markets.router, research.router, about.router): app.include_router(route)
@app.get("/search")
def search(request:Request, q:str=""):
    return templates.TemplateResponse(request,"search_results.html",{"results":data.search_articles(q),"q":q,"seo":{"title":"Search | BudasAI Research","description":"Search BudasAI Research."}})
