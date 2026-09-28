"""SQLAlchemy models for extracted documents and chunks."""

from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class DocumentRecord(Base):
    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_type: Mapped[str] = mapped_column(String(32))
    file_path: Mapped[str] = mapped_column(Text)
    pages: Mapped[int] = mapped_column(Integer)
    text_layer_coverage: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChunkRecord(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(255), index=True)
    page: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[str] = mapped_column(String(128))
    extracted_text: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(32))
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
