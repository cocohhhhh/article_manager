from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, Table, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

# Association table for many-to-many relationship between articles and labels
article_label = Table('article_label', Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id')),
    Column('label_id', Integer, ForeignKey('labels.id'))
)

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    content = Column(Text)  # Store article content
    date_added = Column(DateTime, default=datetime.now)
    date_read = Column(DateTime, nullable=True)
    is_read = Column(Boolean, default=False)
    source_id = Column(Integer, ForeignKey("rss_feeds.id"))
    
    # Relationships
    labels = relationship("Label", secondary=article_label, back_populates="articles")
    highlights = relationship("Highlight", back_populates="article", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="article", cascade="all, delete-orphan")
    source = relationship("RSSFeed", back_populates="articles")

class Label(Base):
    __tablename__ = "labels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    # Relationship with articles
    articles = relationship("Article", secondary=article_label, back_populates="labels")

class Highlight(Base):
    __tablename__ = "highlights"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text)
    start_offset = Column(Integer)  # Position in the article
    end_offset = Column(Integer)
    article_id = Column(Integer, ForeignKey('articles.id'))
    
    article = relationship("Article", back_populates="highlights")
    notes = relationship("Note", back_populates="highlight")

class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    date_created = Column(DateTime)
    article_id = Column(Integer, ForeignKey('articles.id'))
    highlight_id = Column(Integer, ForeignKey('highlights.id'), nullable=True)
    
    article = relationship("Article", back_populates="notes")
    highlight = relationship("Highlight", back_populates="notes")

class RSSFeed(Base):
    __tablename__ = "rss_feeds"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    url = Column(String, unique=True, index=True)
    last_fetched = Column(DateTime, nullable=True)
    date_added = Column(DateTime, default=datetime.now)
    
    articles = relationship("Article", back_populates="source")
