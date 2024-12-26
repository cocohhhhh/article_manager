from fastapi import FastAPI, Request, Form, Depends, HTTPException, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import models
from database import SessionLocal, engine
import schemas
from typing import List, Optional
import feedparser
from bs4 import BeautifulSoup
import json
from datetime import datetime
import random

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def fetch_rss_articles(db: Session):
    feeds = db.query(models.RSSFeed).all()
    new_articles = []
    
    for feed in feeds:
        try:
            parsed_feed = feedparser.parse(feed.url)
            for entry in parsed_feed.entries:
                existing = db.query(models.Article).filter(models.Article.url == entry.link).first()
                if not existing:
                    pub_date = None
                    if hasattr(entry, 'published_parsed'):
                        pub_date = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed'):
                        pub_date = datetime(*entry.updated_parsed[:6])
                    
                    article = models.Article(
                        title=entry.title,
                        url=entry.link,
                        content=BeautifulSoup(entry.description, 'html.parser').get_text(),
                        date_added=pub_date or datetime.now(),
                        source_id=feed.id
                    )
                    new_articles.append(article)
            
            feed.last_fetched = datetime.now()
            db.add(feed)
        except Exception as e:
            print(f"Error fetching feed {feed.url}: {str(e)}")
    
    if new_articles:
        db.bulk_save_objects(new_articles)
    db.commit()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, tag: str = None, db: Session = Depends(get_db)):
    query = db.query(models.Article)
    
    feeds = db.query(models.RSSFeed).all()
    
    if tag:
        query = query.join(models.article_label).join(models.Label).filter(
            models.Label.name == tag
        )
        articles = query.order_by(models.Article.date_added.desc()).all()
    else:
        unread_articles = query.filter(models.Article.is_read == False).all()
        articles = random.sample(unread_articles, min(3, len(unread_articles)))
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    read_days = db.query(models.Article.date_read).filter(
        models.Article.is_read == True,
        models.Article.date_read >= thirty_days_ago
    ).distinct().all()
    read_days = [day[0].strftime('%Y-%m-%d') for day in read_days if day[0]]
    
    labels = db.query(models.Label).all()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "read_days": read_days,
        "labels": labels,
        "articles": articles,
        "selected_tag": tag,
        "now": datetime.now(),
        "timedelta": timedelta,
        "feeds": feeds
    })

@app.get("/article/{article_id}", response_class=HTMLResponse)
async def read_article(request: Request, article_id: int, db: Session = Depends(get_db)):
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    return templates.TemplateResponse(
        "article.html",
        {
            "request": request,
            "article": article,
            "labels": db.query(models.Label).all()
        }
    )

@app.post("/highlight")
async def create_highlight(
    article_id: int,
    text: str,
    start_offset: int,
    end_offset: int,
    db: Session = Depends(get_db)
):
    highlight = models.Highlight(
        text=text,
        start_offset=start_offset,
        end_offset=end_offset,
        article_id=article_id
    )
    db.add(highlight)
    db.commit()
    return {"id": highlight.id}

@app.post("/note")
async def create_note(
    article_id: int,
    content: str,
    highlight_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    note = models.Note(
        content=content,
        article_id=article_id,
        highlight_id=highlight_id,
        date_created=datetime.now()
    )
    db.add(note)
    db.commit()
    return {"id": note.id}

@app.post("/sources")
async def add_source(
    name: str = Form(...),
    url: str = Form(...),
    db: Session = Depends(get_db)
):
    source = models.Source(name=name, url=url)
    db.add(source)
    db.commit()
    
    feed = feedparser.parse(url)
    new_articles = []
    for entry in feed.entries:
        existing = db.query(models.Article).filter(models.Article.url == entry.link).first()
        if not existing:
            pub_date = None
            if hasattr(entry, 'published_parsed'):
                pub_date = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed'):
                pub_date = datetime(*entry.updated_parsed[:6])
            
            article = models.Article(
                title=entry.title,
                url=entry.link,
                content=BeautifulSoup(entry.description, 'html.parser').get_text(),
                date_added=pub_date or datetime.now(),
                source_id=source.id
            )
            new_articles.append(article)
    
    if new_articles:
        db.bulk_save_objects(new_articles)
        db.commit()
    
    return RedirectResponse(url="/", status_code=303)

@app.post("/add-feed")
async def add_feed(feed_url: str = Form(...), db: Session = Depends(get_db)):
    existing = db.query(models.RSSFeed).filter(models.RSSFeed.url == feed_url).first()
    if existing:
        return RedirectResponse(url="/", status_code=303)
    
    try:
        feed_data = feedparser.parse(feed_url)
        if feed_data.bozo:  
            raise ValueError("Invalid RSS feed")
            
        feed = models.RSSFeed(
            url=feed_url,
            name=feed_data.feed.get('title', None),
            date_added=datetime.now()
        )
        db.add(feed)
        db.commit()
        
        await fetch_rss_articles(db)
        
    except Exception as e:
        print(f"Error adding feed: {str(e)}")
        
    return RedirectResponse(url="/", status_code=303)

@app.post("/delete-feed")
async def delete_feed(feed_id: int = Form(...), db: Session = Depends(get_db)):
    feed = db.query(models.RSSFeed).filter(models.RSSFeed.id == feed_id).first()
    if feed:
        db.delete(feed)
        db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/export-notes")
async def export_notes(article_ids: List[int], db: Session = Depends(get_db)):
    notes = db.query(models.Note).filter(
        models.Note.article_id.in_(article_ids)
    ).all()
    
    export_data = []
    for note in notes:
        export_data.append({
            "article_title": note.article.title,
            "note_content": note.content,
            "highlight_text": note.highlight.text if note.highlight else None,
            "date_created": note.date_created.isoformat()
        })
    
    return JSONResponse(content=export_data)

@app.get("/refresh-articles")
async def refresh_articles(request: Request, db: Session = Depends(get_db)):
    tag = request.query_params.get('tag')
    if tag:
        return RedirectResponse(url=f"/?tag={tag}", status_code=303)
    return RedirectResponse(url="/", status_code=303)

@app.post("/add-label")
async def add_label(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    article_id = data.get("article_id")
    label_name = data.get("label_name")

    label = db.query(models.Label).filter(models.Label.name == label_name).first()
    if not label:
        label = models.Label(name=label_name)
        db.add(label)
        db.commit()

    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if not article.is_read:
        article.is_read = True
        article.date_read = datetime.now()

    if label not in article.labels:
        article.labels.append(label)

    db.commit()
    return {"success": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
