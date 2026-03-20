from __future__ import annotations
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Enum, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
from typing import Dict

class User(Base):
    __tablename__ = "users"
    id               = Column(Integer, primary_key=True, index=True)
    email            = Column(String(255), unique=True, index=True, nullable=False)
    name             = Column(String(255), nullable=False)
    password         = Column(String(255), nullable=False)
    tier             = Column(Enum("free", "pro", "agency", name="user_tier"), default="free")
    whatsapp         = Column(String(20), nullable=True)
    company          = Column(String(255), nullable=True)
    is_active        = Column(Boolean, default=True)
    # Quota & Subscription fields
    scans_this_month = Column(Integer, default=0)
    topup_scans      = Column(Integer, default=0)
    last_reset_date  = Column(DateTime, default=func.now())
    subscription_end = Column(DateTime, nullable=True)
    
    created_at       = Column(DateTime, default=func.now())
    updated_at       = Column(DateTime, default=func.now(), onupdate=func.now())
    scans            = relationship("ScanResult", back_populates="user")
    transactions     = relationship("Transaction", back_populates="user")
    projects         = relationship("Project", back_populates="user")

SCAN_LIMITS: Dict[str, int] = {
    "free":   10,
    "pro":    100,
    "agency": 1000
}

class Transaction(Base):
    __tablename__ = "transactions"
    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id"))
    order_id      = Column(String(100), unique=True, index=True)
    amount        = Column(Integer)
    plan_tier     = Column(String(50))
    billing_cycle = Column(String(20), nullable=True)
    status        = Column(String(50), default="pending") # pending, settlement, expire, cancel, deny
    payment_type  = Column(String(50), nullable=True)
    snap_token    = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="transactions")

class Project(Base):
    __tablename__ = "projects"
    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"))
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=func.now())
    
    user  = relationship("User", back_populates="projects")
    scans = relationship("ScanResult", back_populates="project")

class ScanResult(Base):
    __tablename__ = "scan_results"
    id                    = Column(Integer, primary_key=True, index=True)
    user_id               = Column(Integer, ForeignKey("users.id"), nullable=True)
    project_id            = Column(Integer, ForeignKey("projects.id"), nullable=True)
    domain                = Column(String(255), index=True)
    url_scanned           = Column(String(500))
    total_score           = Column(Float, default=0.0)
    seo_score             = Column(Float, default=0.0)
    performance_score     = Column(Float, default=0.0)
    trust_score           = Column(Float, default=0.0)
    content_score         = Column(Float, default=0.0)
    local_seo_score       = Column(Float, default=0.0)
    status                = Column(String(100), nullable=True)
    issues_count_critical = Column(Integer, default=0)
    issues_count_warning  = Column(Integer, default=0)
    issues_count_info     = Column(Integer, default=0)
    issues_json           = Column(Text, nullable=True)
    page_info_json        = Column(Text, nullable=True)
    pagespeed_json        = Column(Text, nullable=True)
    action_plan_json      = Column(Text, nullable=True)
    ai_summary            = Column(Text, nullable=True)
    created_at            = Column(DateTime, default=func.now())
    user                  = relationship("User", back_populates="scans")
    project               = relationship("Project", back_populates="scans")
    
    competitors           = relationship("CompetitorScan", back_populates="scan", cascade="all, delete-orphan")

class CompetitorScan(Base):
    __tablename__ = "competitor_scans"
    id            = Column(Integer, primary_key=True, index=True)
    scan_id       = Column(Integer, ForeignKey("scan_results.id"), index=True)
    domain        = Column(String(255))
    total_score   = Column(Float, default=0.0)
    seo_score     = Column(Float, default=0.0)
    trust_score   = Column(Float, default=0.0)
    content_score = Column(Float, default=0.0)
    local_score   = Column(Float, default=0.0)
    perf_score    = Column(Float, default=0.0)
    created_at    = Column(DateTime, default=func.now())
    
    scan          = relationship("ScanResult", back_populates="competitors")

class LeadCapture(Base):
    __tablename__ = "lead_captures"
    id         = Column(Integer, primary_key=True, index=True)
    email      = Column(String(255), index=True)
    name       = Column(String(255), nullable=True)
    whatsapp   = Column(String(20), nullable=True)
    domain     = Column(String(255))
    scan_id    = Column(Integer, ForeignKey("scan_results.id"), nullable=True)
    source     = Column(String(50), default="free_scan")
    created_at = Column(DateTime, default=func.now())
