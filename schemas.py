from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class LabelBase(BaseModel):
    name: str

class Label(LabelBase):
    id: int
    
    class Config:
        orm_mode = True

class ArticleBase(BaseModel):
    title: str
    url: str

class Article(ArticleBase):
    id: int
    date_added: datetime
    date_read: Optional[datetime]
    is_read: bool
    labels: List[Label] = []
    
    class Config:
        orm_mode = True
