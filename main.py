import sys, os, asyncio
from datetime import datetime, timedelta
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from datetime import datetime
from typing import Optional, Any
from database import get_db, engine
from pydantic import BaseModel
from typing import Optional
from models import ScanResult, User
import models
import json
import os

from auth import (
    hash_password, verify_password, create_token,
    get_current_user, get_optional_user,
    check_scan_limit, increment_scan_count
)
from scanner.crawler import crawl
from scanner.rules import analyze
from scanner.pagespeed import get_pagespeed
from scanner.ai import full_analysis
from scanner.report import build_report
from payment import midtrans_helper
import uuid
from scanner.free_tools import router as free_tools_router

models.Base.metadata.create_all(bind=engine)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="SEO Scanner API — Bang Bisnis", version="2.0.0")
app.state.limiter = limiter
app.include_router(free_tools_router)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://scanner.bangbisnis.id",
        "https://bangbisnis.web.id",
        "https://seo-scanner-frontend.vercel.app", # Placeholder, ganti dengan URL Vercel kamu
        "*" # Sementara perbolehkan semua selama testing deployment
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# ══════════════════════════════════════════
# SCHEMAS
# ══════════════════════════════════════════
class RegisterSchema(BaseModel):
    email:    EmailStr
    name:     str
    password: str
    whatsapp: Optional[str] = None
    company:  Optional[str] = None

class LoginSchema(BaseModel):
    email:    EmailStr
    password: str

class ScanRequest(BaseModel):
    domain: str
    use_ai: bool = False
    project_id: Optional[int] = None

class CompetitorRequest(BaseModel):
    competitors: list[str]

class LeadSchema(BaseModel):
    email:    EmailStr
    name:     Optional[str] = None
    whatsapp: Optional[str] = None
    domain:   str
    scan_id:  Optional[int] = None

class UpdateProfileSchema(BaseModel):
    name: Optional[str] = None
    whatsapp: Optional[str] = None

class CreatePaymentSchema(BaseModel):
    plan_tier: str # pro, agency
    billing_cycle: str # monthly, yearly

class ProjectSchema(BaseModel):
    name: str
    description: Optional[str] = None

class AssignProjectSchema(BaseModel):
    project_id: Optional[int] = None

# ══════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════
@app.post("/auth/register", tags=["Auth"])
@limiter.limit("5/hour")
async def register(request: Request, body: RegisterSchema, db: Session = Depends(get_db)) -> Any:
    if db.query(models.User).filter(models.User.email == body.email).first():
        raise HTTPException(400, "Email sudah terdaftar")
    user = models.User(
        email    = body.email,
        name     = body.name,
        password = hash_password(body.password),
        whatsapp = body.whatsapp,
        company  = body.company,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token({"user_id": user.id, "email": user.email, "tier": user.tier})
    return {
        "message": "Registrasi berhasil",
        "token":   token,
        "user":    {"id": user.id, "name": user.name, "email": user.email, "tier": user.tier}
    }

@app.post("/auth/login", tags=["Auth"])
@limiter.limit("10/minute")
async def login(request: Request, body: LoginSchema, db: Session = Depends(get_db)) -> Any:
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not verify_password(body.password, user.password):
        raise HTTPException(401, "Email atau password salah")
    token = create_token({"user_id": user.id, "email": user.email, "tier": user.tier})
    return {
        "token": token,
        "user":  {
            "id": user.id, "name": user.name, "email": user.email,
            "tier": user.tier,
            "scans_this_month": user.scans_this_month,
            "scan_limit": models.SCAN_LIMITS.get(user.tier, 3)
        }
    }

class GoogleAuthSchema(BaseModel):
    token: str

@app.post("/auth/google", tags=["Auth"])
@limiter.limit("10/minute")
async def google_login(request: Request, body: GoogleAuthSchema, db: Session = Depends(get_db)) -> Any:
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    import secrets
    import os
    
    try:
        CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "717904791336-qj6g02f8jngc2uolvlsst94tll18o4v6.apps.googleusercontent.com")
        try:
            idinfo = id_token.verify_oauth2_token(body.token, google_requests.Request(), CLIENT_ID)
            email = idinfo['email']
            name = idinfo.get('name', 'Google User')
        except Exception as e:
            print(f"ERROR Google Token Verification: {str(e)}")
            raise HTTPException(401, f"Token Google tidak valid: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR in google_login: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(500, f"Internal server error: {str(e)}")
        
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        random_pwd = secrets.token_urlsafe(16)
        user = models.User(
            email=email,
            name=name,
            password=hash_password(random_pwd),
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
    token_val = create_token({"user_id": user.id, "email": user.email, "tier": user.tier})
    return {
        "message": "Login Google berhasil",
        "token": token_val,
        "user": {
            "id": user.id, "name": user.name, "email": user.email,
            "tier": user.tier,
            "scans_this_month": user.scans_this_month,
            "scan_limit": models.SCAN_LIMITS.get(user.tier, 3)
        }
    }


@app.get("/auth/me", tags=["Auth"])
async def me(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    # Auto-sync pending transactions for local dev (webhook might not reach localhost)
    pending_txs = db.query(models.Transaction).filter(
        models.Transaction.user_id == current_user.id,
        models.Transaction.status == "pending"
    ).all()
    
    for tx in pending_txs:
        print(f"DEBUG: Syncing pending transaction {tx.order_id} for user {current_user.id}")
        status_res = midtrans_helper.get_status(tx.order_id)
        if status_res:
            print(f"DEBUG: Midtrans status for {tx.order_id}: {status_res.get('transaction_status')}")
            handle_transaction_status(db, status_res)
        else:
            print(f"DEBUG: No status response from Midtrans for {tx.order_id}")
                
    # Refresh current_user from DB because tier might have changed
    db.refresh(current_user)

    return {
        "id":               current_user.id,
        "name":             current_user.name,
        "email":            current_user.email,
        "tier":             current_user.tier,
        "whatsapp":         current_user.whatsapp,
        "company":          current_user.company,
        "scans_this_month": current_user.scans_this_month,
        "topup_scans":      current_user.topup_scans,
        "scan_limit":       models.SCAN_LIMITS.get(current_user.tier, 3),
        "last_reset_date":  current_user.last_reset_date,
        "subscription_end": current_user.subscription_end,
        "created_at":       current_user.created_at
    }

# ══════════════════════════════════════════
# SCAN
# ══════════════════════════════════════════
@app.post("/scan", tags=["Scanner"])
@limiter.limit("10/minute")
async def scan_website(
    request: Request,
    body: ScanRequest,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_optional_user)
) -> Any:
    domain = body.domain.strip().lower()
    domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
    if not domain:
        raise HTTPException(400, "Domain tidak valid")

    url = f"https://{domain}"

    if current_user:
        if not check_scan_limit(current_user, db):
            limit = models.SCAN_LIMITS.get(current_user.tier, 3)
            raise HTTPException(429, {
                "error":        "scan_limit_exceeded",
                "message":      f"Kamu sudah mencapai batas {limit} scan bulan ini untuk tier {current_user.tier}.",
                "upgrade_url":  "/pricing",
                "whatsapp_url": f"https://wa.me/{os.getenv('WHATSAPP_NUMBER', '6281234567890')}"
            })

    # Parallelize crawl and pagespeed for speed
    crawl_data, pagespeed = await asyncio.gather(
        crawl(url),
        get_pagespeed(url)
    )
    rule_result = analyze(crawl_data, pagespeed)

    ai_data: Optional[dict] = None
    is_pro = current_user is not None and current_user.tier in ["pro", "agency"]
    if body.use_ai and is_pro:
        ai_data = await full_analysis(
            domain,
            rule_result["scores"],
            rule_result["issues"],
            crawl_data,
            pagespeed
        )

    report = build_report(domain, crawl_data, rule_result, pagespeed, ai_data)
    report["meta"]["scanned_at"] = datetime.utcnow().isoformat()

    scan_record = models.ScanResult(
        user_id               = current_user.id if current_user else None,
        domain                = domain,
        url_scanned           = url,
        total_score           = float(rule_result["total_score"]),
        seo_score             = float(rule_result["scores"].get("seo") or 0),
        performance_score     = float(rule_result["scores"].get("performance") or 0),
        trust_score           = float(rule_result["scores"].get("social") or 0),
        content_score         = float(rule_result["scores"].get("content") or 0),
        local_seo_score       = float(rule_result["scores"].get("local") or 0),
        status                = str(report["overview"]["status"]),
        issues_count_critical = int(rule_result["issue_count"]["critical"]),
        issues_count_warning  = int(rule_result["issue_count"]["warning"]),
        issues_count_info     = int(rule_result["issue_count"]["info"]),
        issues_json           = json.dumps(rule_result["issues"], ensure_ascii=False),
        page_info_json        = json.dumps(report["page_info"], ensure_ascii=False),
        pagespeed_json        = json.dumps(report["performance"], ensure_ascii=False),
        action_plan_json      = json.dumps(report["action_plan"], ensure_ascii=False),
        ai_summary            = json.dumps(ai_data, ensure_ascii=False) if ai_data else None,
    )
    db.add(scan_record)
    db.commit()
    db.refresh(scan_record)

    if current_user:
        increment_scan_count(current_user, db)

    report["scan_id"] = scan_record.id

    if not current_user or current_user.tier == "free":
        report["issues"]["all"]      = report["issues"]["all"][:5]
        report["issues"]["critical"] = report["issues"]["critical"][:3]
        report["issues"]["warnings"] = report["issues"]["warnings"][:2]
        report["issues"]["info"]     = []
        report["action_plan"]["fix_this_week"] = []
        report["action_plan"]["fix_later"]     = []
        report["ai_insights"]["available"]     = False
        report["_gated"]        = True
        report["_gate_message"] = "Upgrade ke Pro untuk melihat semua issue dan rekomendasi lengkap."

    return report

@app.get("/scan/{scan_id}", tags=["Scanner"])
async def get_scan_result(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_optional_user)
) -> Any:
    record = db.query(models.ScanResult).filter(models.ScanResult.id == scan_id).first()
    if not record:
        raise HTTPException(404, "Scan tidak ditemukan")
    return {
        "scan_id":          record.id,
        "domain":           record.domain,
        "total_score":      record.total_score,
        "seo_score":        record.seo_score,
        "performance_score": record.performance_score,
        "trust_score":      record.trust_score,
        "content_score":    record.content_score,
        "local_seo_score":  record.local_seo_score,
        "status":           record.status,
        "issue_counts": {
            "critical": record.issues_count_critical,
            "warning":  record.issues_count_warning,
            "info":     record.issues_count_info,
        },
        "issues":      json.loads(record.issues_json or "[]"),
        "page_info":   json.loads(record.page_info_json or "{}"),
        "action_plan": json.loads(record.action_plan_json or "{}"),
        "ai_summary":  json.loads(record.ai_summary) if record.ai_summary else None,
        "scanned_at":  record.created_at,
    }

@app.post("/scan/{scan_id}/competitors", tags=["Scanner"])
@limiter.limit("5/minute")
async def analyze_competitors(
    request: Request,
    scan_id: int,
    body: CompetitorRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    if current_user.tier not in ["pro", "agency"]:
        raise HTTPException(403, "Fitur ini khusus untuk pengguna Pro dan Agency.")
    
    # Verify scan belongs to user
    scan_record = db.query(models.ScanResult).filter(models.ScanResult.id == scan_id, models.ScanResult.user_id == current_user.id).first()
    if not scan_record:
        raise HTTPException(404, "Scan utama tidak ditemukan")
        
    comp_limit = 10 if current_user.tier == "agency" else 3
    if not body.competitors or len(body.competitors) > comp_limit:
        raise HTTPException(400, f"Maksimal {comp_limit} kompetitor untuk paket {current_user.tier.capitalize()}.")

    # Delete existing competitors for this scan to replace them
    db.query(models.CompetitorScan).filter(models.CompetitorScan.scan_id == scan_id).delete()
    
    import asyncio
    
    async def process_competitor(comp_domain: str):
        comp_domain = comp_domain.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
        if not comp_domain:
            return None
        comp_url = f"https://{comp_domain}"
        try:
            c_data = await crawl(comp_url)
            p_data = await get_pagespeed(comp_url)
            c_rule = analyze(c_data, p_data)
            return models.CompetitorScan(
                scan_id       = scan_id,
                domain        = comp_domain,
                total_score   = float(c_rule["total_score"]),
                seo_score     = float(c_rule["scores"].get("seo") or 0),
                perf_score    = float(c_rule["scores"].get("performance") or 0),
                trust_score   = float(c_rule["scores"].get("social") or 0),
                content_score = float(c_rule["scores"].get("content") or 0),
                local_score   = float(c_rule["scores"].get("local") or 0)
            )
        except Exception as e:
            print(f"Error scanning competitor {comp_domain}: {e}")
            return None

    tasks = [process_competitor(d) for d in body.competitors]
    results = await asyncio.gather(*tasks)
    
    saved_comps = []
    for comp in results:
        if comp:
            db.add(comp)
            saved_comps.append(comp)
            
    db.commit()
    
    return [
        {
            "domain": c.domain,
            "total_score": c.total_score,
            "seo_score": c.seo_score,
            "trust_score": c.trust_score,
            "content_score": c.content_score,
            "local_score": c.local_score,
            "perf_score": c.perf_score
        } for c in saved_comps
    ]

@app.get("/scan/{scan_id}/competitors", tags=["Scanner"])
async def get_competitors(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    # Verify scan belongs to user
    scan_record = db.query(models.ScanResult).filter(models.ScanResult.id == scan_id, models.ScanResult.user_id == current_user.id).first()
    if not scan_record:
        raise HTTPException(404, "Scan utama tidak ditemukan")
        
    comps = db.query(models.CompetitorScan).filter(models.CompetitorScan.scan_id == scan_id).all()
    return [
        {
            "domain": c.domain,
            "total_score": c.total_score,
            "seo_score": c.seo_score,
            "trust_score": c.trust_score,
            "content_score": c.content_score,
            "local_score": c.local_score,
            "perf_score": c.perf_score
        } for c in comps
    ]

@app.get("/scans/history", tags=["Scanner"])
async def scan_history(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 20
) -> Any:
    scans = (
        db.query(models.ScanResult)
        .filter(models.ScanResult.user_id == current_user.id)
        .order_by(models.ScanResult.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{
        "scan_id":     s.id,
        "domain":      s.domain,
        "total_score": s.total_score,
        "status":      s.status,
        "critical":    s.issues_count_critical,
        "warning":     s.issues_count_warning,
        "scanned_at":  s.created_at,
    } for s in scans]

# ══════════════════════════════════════════
# LEAD CAPTURE
# ══════════════════════════════════════════
@app.post("/lead", tags=["Marketing"])
async def capture_lead(body: LeadSchema, db: Session = Depends(get_db)) -> Any:
    lead = models.LeadCapture(
        email    = body.email,
        name     = body.name,
        whatsapp = body.whatsapp,
        domain   = body.domain,
        scan_id  = body.scan_id,
    )
    db.add(lead)
    db.commit()
    return {"message": "Terima kasih! Tim kami akan menghubungi kamu segera."}

@app.get("/leads", tags=["Admin"])
async def get_leads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    admin_emails = os.getenv("ADMIN_EMAILS", "").split(",")
    if current_user.email not in admin_emails:
        raise HTTPException(403, "Akses ditolak")
    leads = (
        db.query(models.LeadCapture)
        .order_by(models.LeadCapture.created_at.desc())
        .limit(100)
        .all()
    )
    return [{
        "id":         l.id,
        "email":      l.email,
        "name":       l.name,
        "whatsapp":   l.whatsapp,
        "domain":     l.domain,
        "created_at": l.created_at
    } for l in leads]

# ══════════════════════════════════════════
# PROJECTS
# ══════════════════════════════════════════
@app.post("/projects", tags=["Projects"])
async def create_project(
    body: ProjectSchema,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    project = models.Project(
        user_id     = current_user.id,
        name        = body.name,
        description = body.description
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at
    }

@app.get("/projects", tags=["Projects"])
async def get_projects(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    projects = db.query(models.Project).filter(models.Project.user_id == current_user.id).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "created_at": p.created_at
        } for p in projects
    ]

@app.get("/projects/{project_id}", tags=["Projects"])
async def get_project_details(
    project_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(404, "Project tidak ditemukan")
    
    scans = db.query(models.ScanResult).filter(models.ScanResult.project_id == project_id).all()
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "created_at": project.created_at
        },
        "scans": [
            {
                "id": s.id,
                "domain": s.domain,
                "total_score": s.total_score,
                "created_at": s.created_at
            } for s in scans
        ]
    }

@app.put("/projects/{project_id}", tags=["Projects"])
async def update_project(
    project_id: int,
    body: ProjectSchema,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    project = db.query(models.Project).filter(
        models.Project.id == project_id, 
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(404, "Project tidak ditemukan")
    
    project.name = body.name
    project.description = body.description
    db.commit()
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at
    }

@app.delete("/projects/{project_id}", tags=["Projects"])
async def delete_project(
    project_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(404, "Project tidak ditemukan")
    
    # Detach scans
    db.query(models.ScanResult).filter(models.ScanResult.project_id == project_id).update({"project_id": None})
    db.delete(project)
    db.commit()
    return {"message": "Project berhasil dihapus"}

@app.post("/scan/{scan_id}/assign-project", tags=["Projects"])
async def assign_project(
    scan_id: int,
    body: AssignProjectSchema,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    scan = db.query(models.ScanResult).filter(
        models.ScanResult.id == scan_id,
        models.ScanResult.user_id == current_user.id
    ).first()
    if not scan:
        raise HTTPException(404, "Scan tidak ditemukan")
    
    if body.project_id:
        project = db.query(models.Project).filter(
            models.Project.id == body.project_id,
            models.Project.user_id == current_user.id
        ).first()
        if not project:
            raise HTTPException(404, "Project tujuan tidak ditemukan")
            
    scan.project_id = body.project_id
    db.commit()
    return {"message": "Berhasil memindahkan scan ke project"}

# ══════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════
@app.get("/", tags=["Health"])
def health() -> Any:
    return {
        "status":  "ok",
        "product": os.getenv("APP_NAME", "SEO Scanner"),
        "version": "2.0.0",
        "docs":    "/docs"
    }

# ══════════════════════════════════════════
# PROFILE
# ══════════════════════════════════════════
@app.put("/auth/profile", tags=["Auth"])
def update_profile(
    body: UpdateProfileSchema,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if body.name and body.name.strip():
        user.name = body.name.strip()
    if body.whatsapp is not None:
        user.whatsapp = body.whatsapp.strip()
    db.commit()
    db.refresh(user)
    return {
        "id":               user.id,
        "name":             user.name,
        "email":            user.email,
        "whatsapp":         user.whatsapp,
        "tier":             user.tier,
        "scan_limit":       models.SCAN_LIMITS.get(user.tier, 3),
        "scans_this_month": user.scans_this_month,
    }

# ══════════════════════════════════════════
# EXPORT PDF
# ══════════════════════════════════════════
@app.get("/scan/{scan_id}/export-pdf", tags=["Scanner"])
async def export_pdf(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    record = db.query(models.ScanResult).filter(models.ScanResult.id == scan_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Scan tidak ditemukan")
    if current_user.tier == "free":
        raise HTTPException(status_code=403, detail="Upgrade ke Pro untuk export PDF")

    try:
        import json
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER

        page_info = json.loads(record.page_info_json or "{}")
        action_plan = json.loads(record.action_plan_json or "{}")

        # ── COLORS (semua pakai HexColor, tidak ada hexval()) ──
        C_GREEN    = colors.HexColor('#059669')
        C_GREEN_L  = colors.HexColor('#d1fae5')
        C_RED      = colors.HexColor('#dc2626')
        C_RED_L    = colors.HexColor('#fee2e2')
        C_YELLOW   = colors.HexColor('#d97706')
        C_YELLOW_L = colors.HexColor('#fef3c7')
        C_BLUE_L   = colors.HexColor('#dbeafe')
        C_GRAY     = colors.HexColor('#6b7280')
        C_DARK     = colors.HexColor('#111827')
        C_BG       = colors.HexColor('#f9fafb')
        C_BORDER   = colors.HexColor('#e5e7eb')

        # Helper: return HexColor object berdasarkan score
        def sc(val):
            if val >= 80: return C_GREEN
            if val >= 60: return C_YELLOW
            return C_RED

        # Helper: return hex string (tanpa #) berdasarkan score
        def sc_hex(val):
            if val >= 80: return '059669'
            if val >= 60: return 'd97706'
            return 'dc2626'

        styles = getSampleStyleSheet()

        def sty(name, **kw):
            return ParagraphStyle(name, parent=styles['Normal'], **kw)

        S_H2   = sty('h2', fontSize=13, fontName='Helvetica-Bold', textColor=C_DARK, spaceBefore=14, spaceAfter=6)
        S_BODY = sty('body', fontSize=9, fontName='Helvetica', textColor=C_DARK, leading=13)

        buffer = BytesIO()
        PAGE_W, PAGE_H = A4
        MARGIN = 0.6 * inch
        W = PAGE_W - 2 * MARGIN

        def on_first_page(canvas, doc):
            _draw_footer(canvas, doc)

        def on_later_pages(canvas, doc):
            canvas.saveState()
            canvas.setFillColor(C_GREEN)
            canvas.rect(0, PAGE_H - 0.45*inch, PAGE_W, 0.45*inch, fill=1, stroke=0)
            canvas.setFont('Helvetica-Bold', 9)
            canvas.setFillColor(colors.white)
            canvas.drawString(MARGIN, PAGE_H - 0.28*inch, f"SEO Audit Report  |  {record.domain}")
            canvas.setFont('Helvetica', 9)
            canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.28*inch, f"Halaman {doc.page}")
            canvas.restoreState()
            _draw_footer(canvas, doc)

        def _draw_footer(canvas, doc):
            canvas.saveState()
            canvas.setStrokeColor(C_BORDER)
            canvas.setLineWidth(0.5)
            canvas.line(MARGIN, 0.45*inch, PAGE_W - MARGIN, 0.45*inch)
            canvas.setFont('Helvetica', 7)
            canvas.setFillColor(C_GRAY)
            canvas.drawString(MARGIN, 0.28*inch, "SEO Scanner by Bang Bisnis  |  Laporan bersifat rahasia untuk penerima yang dituju.")
            canvas.drawRightString(PAGE_W - MARGIN, 0.28*inch, "© 2026 Bang Bisnis")
            canvas.restoreState()

        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=MARGIN, leftMargin=MARGIN,
            topMargin=0.6*inch, bottomMargin=0.65*inch,
        )

        story = []

        # ══ HERO BANNER ══
        hero_table = Table([[
            Paragraph("SEO Audit Report", sty('t', fontSize=26, fontName='Helvetica-Bold', textColor=colors.white, leading=30)),
        ]], colWidths=[W])
        hero_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), C_GREEN),
            ('TOPPADDING', (0,0), (-1,-1), 22),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 18),
        ]))
        story.append(hero_table)

        sub_table = Table([[
            Paragraph(f"🌐 {record.domain}", sty('d', fontSize=14, fontName='Helvetica-Bold', textColor=C_DARK)),
            Paragraph(f"Scan ID: {record.id}\n{record.created_at.strftime('%d %B %Y, %H:%M WIB')}", sty('dt', fontSize=8, fontName='Helvetica', textColor=C_GRAY, leading=12, alignment=TA_CENTER)),
        ]], colWidths=[W*0.65, W*0.35])
        sub_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), C_BG),
            ('TOPPADDING', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('LEFTPADDING', (0,0), (-1,-1), 18),
            ('RIGHTPADDING', (0,0), (-1,-1), 18),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LINEBELOW', (0,0), (-1,-1), 1, C_BORDER),
        ]))
        story.append(sub_table)
        story.append(Spacer(1, 0.2*inch))

        # ══ SCORE CARDS ══
        total_hex = sc_hex(record.total_score)
        score_cards_data = [[
            Table([
                [Paragraph("<font size=8 color='#6b7280'>TOTAL SCORE</font>", styles['Normal'])],
                [Paragraph(f"<font size=40 color='#{total_hex}'><b>{int(record.total_score)}</b></font>", styles['Normal'])],
                [Paragraph("<font size=8 color='#9ca3af'>/100</font>", styles['Normal'])],
            ], colWidths=[W*0.22]),
            Table([
                [Paragraph("<font size=7 color='#6b7280'>SEO</font>", styles['Normal']),
                Paragraph("<font size=7 color='#6b7280'>Trust</font>", styles['Normal']),
                Paragraph("<font size=7 color='#6b7280'>Konten</font>", styles['Normal']),
                Paragraph("<font size=7 color='#6b7280'>Performa</font>", styles['Normal']),
                Paragraph("<font size=7 color='#6b7280'>Local SEO</font>", styles['Normal'])],
                [Paragraph(f"<font size=18 color='#{sc_hex(record.seo_score)}'><b>{int(record.seo_score)}</b></font>", styles['Normal']),
                Paragraph(f"<font size=18 color='#{sc_hex(record.trust_score)}'><b>{int(record.trust_score)}</b></font>", styles['Normal']),
                Paragraph(f"<font size=18 color='#{sc_hex(record.content_score)}'><b>{int(record.content_score)}</b></font>", styles['Normal']),
                Paragraph(f"<font size=18 color='#{sc_hex(record.performance_score)}'><b>{int(record.performance_score)}</b></font>", styles['Normal']),
                Paragraph(f"<font size=18 color='#{sc_hex(record.local_seo_score)}'><b>{int(record.local_seo_score)}</b></font>", styles['Normal'])],
                [Paragraph(f"<font size=7 color='#dc2626'>[!] {record.issues_count_critical} Kritis</font>", styles['Normal']),
                Paragraph(f"<font size=7 color='#d97706'>[~] {record.issues_count_warning} Peringatan</font>", styles['Normal']),
                Paragraph(f"<font size=7 color='#2563eb'>[i] {record.issues_count_info} Info</font>", styles['Normal']),
                Paragraph("", styles['Normal']),
                Paragraph("", styles['Normal'])],
            ], colWidths=[(W*0.78)/5]*5),
        ]]
        score_main = Table(score_cards_data, colWidths=[W*0.22, W*0.78])
        score_main.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, C_BORDER),
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(score_main)
        story.append(Spacer(1, 0.2*inch))

        # ══ RANKING ESTIMATE ══
        ts = record.total_score
        if ts >= 85:
            rank_lbl, rank_c, rank_bg = "🏆 Potensi Halaman 1 Google", C_GREEN, C_GREEN_L
            rank_desc = "SEO sudah sangat kompetitif. Fokus ke keyword targeting & backlink building."
        elif ts >= 70:
            rank_lbl, rank_c, rank_bg = "🥈 Potensi Halaman 2–3 Google", C_YELLOW, C_YELLOW_L
            rank_desc = "Butuh beberapa perbaikan untuk masuk halaman 1 Google Indonesia."
        elif ts >= 55:
            rank_lbl, rank_c, rank_bg = "🥉 Estimasi Halaman 4–10 Google", C_YELLOW, C_YELLOW_L
            rank_desc = "Perbaikan signifikan dibutuhkan. Prioritaskan semua issue Critical."
        else:
            rank_lbl, rank_c, rank_bg = "⚠️ Belum Terindeks Optimal", C_RED, C_RED_L
            rank_desc = "Skor terlalu rendah. Website belum siap bersaing di hasil pencarian."

        rank_t = Table([[Paragraph(
            f"<font size=8 color='#6b7280'>ESTIMASI POSISI GOOGLE INDONESIA</font><br/>"
            f"<font size=13><b>{rank_lbl}</b></font><br/>"
            f"<font size=8 color='#374151'>{rank_desc}</font>",
            styles['Normal']
        )]], colWidths=[W])
        rank_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), rank_bg),
            ('TOPPADDING', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('LEFTPADDING', (0,0), (-1,-1), 16),
            ('BOX', (0,0), (-1,-1), 1.5, rank_c),
        ]))
        story.append(rank_t)
        story.append(Spacer(1, 0.2*inch))

        # ══ DO'S & DON'TS ══
        story.append(Paragraph(f"✅ Do's & ❌ Don'ts untuk {record.domain}", S_H2))
        pi = page_info
        dos, donts = [], []
        if pi.get('title'): dos.append("Pertahankan title tag yang sudah ada")
        else: donts.append("Jangan biarkan halaman tanpa title tag")
        if pi.get('meta_description'): dos.append("Meta desc sudah ada — pastikan ada keyword utama")
        else: donts.append("Jangan biarkan halaman tanpa meta description")
        if pi.get('h1_tags'): dos.append("H1 sudah ada — gunakan keyword utama di dalamnya")
        else: donts.append("Jangan luncurkan halaman tanpa H1 tag")
        if pi.get('has_sitemap'): dos.append("Sitemap ada — submit rutin ke Google Search Console")
        else: donts.append("Jangan abaikan sitemap — Google butuh ini untuk crawl")
        if pi.get('has_schema'): dos.append("Schema markup ada — tambah lebih banyak tipe schema")
        else: donts.append("Jangan skip schema markup — sinyal kepercayaan penting")
        if pi.get('has_robots_txt'): dos.append("robots.txt ada — jangan blokir halaman penting")
        else: donts.append("Jangan lupa buat robots.txt")
        if pi.get('internal_links', 0) >= 3: dos.append("Internal links cukup — terus tambah untuk PageRank")
        else: donts.append("Jangan buat halaman tanpa minimal 3 internal link")
        if pi.get('word_count', 0) >= 300: dos.append("Konten cukup panjang — jaga kualitas & relevansi")
        else: donts.append(f"Jangan publish konten di bawah 300 kata (sekarang {pi.get('word_count',0)} kata)")
        dos.append("Rutin update konten blog minimal 1–2x per bulan")
        dos.append("Minta review Google dari pelanggan yang puas")
        donts.append("Jangan copy-paste konten dari website lain")
        donts.append("Jangan beli backlink — bisa kena penalty Google")

        max_rows = max(len(dos), len(donts))
        dd_data = [
            [Paragraph("✅ DO'S", sty('dh', fontSize=10, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER)),
             Paragraph("❌ DON'TS", sty('dth', fontSize=10, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER))]
        ]
        for i in range(max_rows):
            d  = Paragraph(f"• {dos[i]}"   if i < len(dos)   else "", sty(f'do{i}',   fontSize=8, textColor=colors.HexColor('#065f46'), leading=12))
            dn = Paragraph(f"• {donts[i]}" if i < len(donts) else "", sty(f'dnt{i}',  fontSize=8, textColor=colors.HexColor('#7f1d1d'), leading=12))
            dd_data.append([d, dn])

        dd_t = Table(dd_data, colWidths=[W/2, W/2])
        dd_style = [
            ('BACKGROUND', (0,0), (0,0), C_GREEN),
            ('BACKGROUND', (1,0), (1,0), C_RED),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('GRID', (0,0), (-1,-1), 0.3, C_BORDER),
            ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ]
        for i in range(1, max_rows+1):
            if i % 2 == 0:
                dd_style.append(('BACKGROUND', (0,i), (0,i), C_GREEN_L))
                dd_style.append(('BACKGROUND', (1,i), (1,i), C_RED_L))
        dd_t.setStyle(TableStyle(dd_style))
        story.append(dd_t)
        story.append(Spacer(1, 0.2*inch))

        # ══ ACTION PLAN ══
        story.append(Paragraph("🎯 Action Plan Prioritas", S_H2))
        ap_rows = [["#", "Issue", "Prioritas", "Dampak"]]
        items = []
        for x in action_plan.get('fix_now', []):      items.append((x.get('issue',''), '🔴 Fix Sekarang', 'Tinggi', C_RED_L))
        for x in action_plan.get('fix_this_week', []): items.append((x.get('issue',''), '🟡 Minggu Ini',   'Sedang', C_YELLOW_L))
        for x in action_plan.get('fix_later', []):    items.append((x.get('issue',''), '🔵 Nanti',        'Rendah', C_BLUE_L))

        for idx, (issue, prio, dampak, bg) in enumerate(items[:15], 1):
            ap_rows.append([
                Paragraph(f"<b>{idx}</b>", sty(f'n{idx}', fontSize=8, fontName='Helvetica-Bold', alignment=TA_CENTER)),
                Paragraph(issue[:80], sty(f'i{idx}', fontSize=8, leading=11)),
                Paragraph(prio, sty(f'p{idx}', fontSize=8, fontName='Helvetica-Bold')),
                Paragraph(dampak, sty(f'd{idx}', fontSize=8, textColor=C_GRAY)),
            ])

        ap_t = Table(ap_rows, colWidths=[0.3*inch, W*0.58, 1.2*inch, 0.7*inch])
        ap_style = [
            ('BACKGROUND', (0,0), (-1,0), C_DARK),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('ALIGN', (0,1), (0,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.3, C_BORDER),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_BG]),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]
        for i, (_, _, _, bg) in enumerate(items[:15], 1):
            ap_style.append(('BACKGROUND', (2,i), (2,i), bg))
        ap_t.setStyle(TableStyle(ap_style))
        story.append(ap_t)
        story.append(Spacer(1, 0.2*inch))

        # ══ ROADMAP ══
        story.append(Paragraph("🗺️ Roadmap 3 Bulan Menuju Halaman 1 Google", S_H2))
        m1, m2 = [], []
        if not pi.get('h1_tags'):         m1.append("Tambahkan H1 dengan keyword utama")
        if pi.get('word_count',0) < 300:  m1.append(f"Perbanyak konten ke 300+ kata")
        if not pi.get('has_sitemap'):     m1.append("Buat sitemap.xml & submit ke GSC")
        if not pi.get('has_robots_txt'):  m1.append("Buat file robots.txt")
        if not pi.get('has_schema'):      m1.append("Tambahkan schema markup JSON-LD")
        if not pi.get('meta_description'):m1.append("Tambahkan meta description 120–155 kar")
        if not m1:                        m1.append("Pertahankan fondasi teknikal yang sudah baik")
        if not pi.get('has_contact_info'):m2.append("Tambahkan info kontak di footer (NAP)")
        if not pi.get('google_maps'):     m2.append("Embed Google Maps di halaman")
        m2.append("Daftarkan ke Google Search Console")
        m2.append("Buat atau klaim Google Business Profile")
        m3 = ["Dapatkan backlink dari direktori bisnis ID", "Minta review Google dari pelanggan", "Rutin buat konten blog 1–2x per bulan", "Targetkan 3–5 keyword long-tail lokal"]

        def road_cell(month, title, items_list, border_c, bg_c):
            rows = [[Paragraph(month, sty('rm', fontSize=7, fontName='Helvetica-Bold', textColor=border_c))],
                    [Paragraph(title, sty('rt', fontSize=10, fontName='Helvetica-Bold', textColor=C_DARK))]]
            for j, x in enumerate(items_list):
                rows.append([Paragraph(f"→ {x}", sty(f'ri{j}', fontSize=8, leading=12, textColor=colors.HexColor('#374151')))])
            t = Table(rows, colWidths=[W/3 - 10])
            t.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
            return t

        road_t = Table([[
            road_cell("BULAN 1", "🔧 Fondasi Teknikal", m1, C_RED, C_RED_L),
            road_cell("BULAN 2", "📍 Optimasi & Local SEO", m2, C_YELLOW, C_YELLOW_L),
            road_cell("BULAN 3", "📈 Authority & Konten", m3, C_GREEN, C_GREEN_L),
        ]], colWidths=[W/3]*3)
        road_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,0), C_RED_L),
            ('BACKGROUND', (1,0), (1,0), C_YELLOW_L),
            ('BACKGROUND', (2,0), (2,0), C_GREEN_L),
            ('BOX', (0,0), (0,0), 1.5, C_RED),
            ('BOX', (1,0), (1,0), 1.5, C_YELLOW),
            ('BOX', (2,0), (2,0), 1.5, C_GREEN),
            ('TOPPADDING', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(road_t)
        story.append(Spacer(1, 0.2*inch))

        # ══ PAGE INFO TABLE ══
        story.append(Paragraph("📄 Detail Informasi Halaman", S_H2))
        pi_rows = [["Attribute", "Nilai", "Status"]]
        pi_items = [
            ("Title Tag",       (pi.get('title') or '')[:55] or "—",                                    bool(pi.get('title'))),
            ("Panjang Title",   f"{pi.get('title_length',0)} kar (ideal 50–60)",                         50 <= pi.get('title_length',0) <= 60),
            ("Meta Description",(pi.get('meta_description') or '')[:55] or "—",                         bool(pi.get('meta_description'))),
            ("Panjang Meta",    f"{pi.get('meta_desc_length',0)} kar (ideal 120–155)",                   120 <= pi.get('meta_desc_length',0) <= 155),
            ("H1 Tag",          (pi.get('h1_tags') or ['—'])[0][:55],                                   bool(pi.get('h1_tags'))),
            ("Jumlah Kata",     f"{pi.get('word_count',0)} kata",                                        pi.get('word_count',0) >= 300),
            ("Total Gambar",    f"{pi.get('total_images',0)} gambar, {pi.get('images_without_alt',0)} tanpa alt", pi.get('images_without_alt',1) == 0),
            ("Internal Links",  f"{pi.get('internal_links',0)} link",                                   pi.get('internal_links',0) >= 3),
            ("Sitemap XML",     "Ada" if pi.get('has_sitemap') else "Tidak ada",                         bool(pi.get('has_sitemap'))),
            ("robots.txt",      "Ada" if pi.get('has_robots_txt') else "Tidak ada",                     bool(pi.get('has_robots_txt'))),
            ("Schema Markup",   f"Ada: {', '.join(pi.get('schema_types',[]))}" if pi.get('has_schema') else "Tidak ada", bool(pi.get('has_schema'))),
            ("Open Graph",      "Lengkap" if pi.get('og_complete') else "Tidak lengkap",                bool(pi.get('og_complete'))),
            ("Mobile Viewport", "Ada" if pi.get('has_viewport') else "Tidak ada",                       bool(pi.get('has_viewport'))),
            ("Canonical URL",   pi.get('canonical') or "Tidak ada",                                     bool(pi.get('canonical'))),
            ("Info Kontak",     "Ditemukan" if pi.get('has_contact_info') else "Tidak ada",              bool(pi.get('has_contact_info'))),
            ("Google Maps",     "Ada" if pi.get('google_maps') else "Tidak ada",                        bool(pi.get('google_maps'))),
        ]
        for attr, val, ok in pi_items:
            status = Paragraph("✅ OK" if ok else "❌ Missing",
                sty('st', fontSize=8, fontName='Helvetica-Bold',
                    textColor=C_GREEN if ok else C_RED, alignment=TA_CENTER))
            pi_rows.append([
                Paragraph(attr, sty('pa', fontSize=8, fontName='Helvetica-Bold', textColor=C_DARK)),
                Paragraph(str(val), sty('pv', fontSize=8, textColor=C_GRAY, leading=11)),
                status,
            ])
        pi_t = Table(pi_rows, colWidths=[1.7*inch, W - 2.7*inch, 0.85*inch])
        pi_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), C_DARK),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('ALIGN', (2,1), (2,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.3, C_BORDER),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_BG]),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(pi_t)
        story.append(Spacer(1, 0.25*inch))

        # ══ CTA FOOTER ══
        cta_t = Table([[Paragraph(
            "<font size=11 color='white'><b>Butuh bantuan implementasi semua rekomendasi ini?</b></font><br/>"
            "<font size=9 color='#d1fae5'>Tim SEO Bang Bisnis siap bantu optimasi dari A–Z.</font><br/>"
            f"<font size=9 color='#a7f3d0'>💬 WA: 0812-3456-7890  |  🌐 scanner.bangbisnis.id</font>",
            styles['Normal']
        )]], colWidths=[W])
        cta_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), C_GREEN),
            ('TOPPADDING', (0,0), (-1,-1), 16),
            ('BOTTOMPADDING', (0,0), (-1,-1), 16),
            ('LEFTPADDING', (0,0), (-1,-1), 20),
            ('RIGHTPADDING', (0,0), (-1,-1), 20),
        ]))
        story.append(cta_t)

        doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages)
        buffer.seek(0)

        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=seo-audit-{record.domain}-{record.id}.pdf"}
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Gagal generate PDF: {str(e)}")

# ══════════════════════════════════════════
# PAYMENT (MIDTRANS)
# ══════════════════════════════════════════
@app.post("/payment/create", tags=["Payment"])
async def create_payment(
    body: CreatePaymentSchema,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    try:
        # 1. Validation
        if body.plan_tier not in ["pro", "agency", "topup_20", "topup_50"]:
            raise HTTPException(400, "Plan tidak valid")
        if body.billing_cycle not in ["monthly", "yearly"]:
            raise HTTPException(400, "Siklus billing tidak valid")

        # 2. Determine Price
        prices = {
            "pro":       {"monthly": 89000,  "yearly": 890000},
            "agency":    {"monthly": 229000, "yearly": 2290000},
            "topup_20":  {"monthly": 15000,  "yearly": 15000},  # reuse monthly key
            "topup_50":  {"monthly": 30000,  "yearly": 30000}
        }
        
        if body.plan_tier.startswith("topup_"):
            amount = prices[body.plan_tier]["monthly"]
        else:
            amount = prices[body.plan_tier][body.billing_cycle]

        # 3. Create Transaction Record
        order_id = f"ORDER-{uuid.uuid4().hex[:8].upper()}"
        new_tx = models.Transaction(
            user_id       = current_user.id,
            order_id      = order_id,
            amount        = amount,
            plan_tier     = body.plan_tier,
            billing_cycle = body.billing_cycle,
            status        = "pending"
        )
        db.add(new_tx)
        db.commit()

        # 4. Call Midtrans
        customer_details = {
            "first_name": current_user.name,
            "email":      current_user.email,
            "phone":      current_user.whatsapp or ""
        }
        
        item_name = f"SEO Scanner {body.plan_tier.capitalize()}"
        if body.plan_tier.startswith("topup_"):
            scans = body.plan_tier.split("_")[1]
            item_name = f"Top-up {scans} Scans"
        else:
            item_name += f" ({body.billing_cycle})"

        item_details = [{
            "id":    f"{body.plan_tier}_{body.billing_cycle}",
            "price": amount,
            "quantity": 1,
            "name": item_name
        }]
        
        midtrans_res = midtrans_helper.create_transaction(order_id, amount, customer_details, item_details)
        if not midtrans_res:
            db.delete(new_tx)
            db.commit()
            raise HTTPException(500, "Gagal terhubung ke gateway pembayaran")

        # 5. Save Snap Token
        new_tx.snap_token = midtrans_res["token"]
        db.commit()

        return {
            "order_id":   order_id,
            "snap_token": midtrans_res["token"],
            "redirect_url": midtrans_res["redirect_url"]
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Error internal: {str(e)}")

def handle_transaction_status(db: Session, status_response: dict):
    order_id = status_response["order_id"]
    transaction_status = status_response["transaction_status"]
    fraud_status = status_response.get("fraud_status")

    tx = db.query(models.Transaction).filter(models.Transaction.order_id == order_id).first()
    if not tx:
        return None

    # Update status
    tx.status = transaction_status
    tx.payment_type = status_response.get("payment_type")
    
    # Logic for successful payment
    if transaction_status == "capture":
        if fraud_status == "challenge":
            tx.status = "challenge"
        elif fraud_status == "accept":
            tx.status = "settlement"
    elif transaction_status == "settlement":
        tx.status = "settlement"
    elif transaction_status in ["cancel", "deny", "expire"]:
        tx.status = transaction_status
    elif transaction_status == "pending":
        tx.status = "pending"

    # If settled, update User data
    if tx.status == "settlement":
        user = db.query(models.User).filter(models.User.id == tx.user_id).first()
        if user:
            # Handle Top-up
            if tx.plan_tier.startswith("topup_"):
                scans = int(tx.plan_tier.split("_")[1])
                user.topup_scans += scans
            else:
                # Handle Subscription
                user.tier = tx.plan_tier
                # Initialize last_reset_date if moving from free or if None
                if not user.last_reset_date or user.tier == "free":
                    user.last_reset_date = datetime.now()
                
                # Calculate subscription end date
                days = 30 if tx.billing_cycle == "monthly" else 365
                if user.subscription_end and user.subscription_end > datetime.now():
                    user.subscription_end += timedelta(days=days)
                else:
                    user.subscription_end = datetime.now() + timedelta(days=days)
    
    db.commit()
    return tx

@app.post("/payment/notification", tags=["Payment"])
async def payment_notification(request: Request, db: Session = Depends(get_db)) -> Any:
    data = await request.json()
    status_response = midtrans_helper.verify_notification(data)
    
    if not status_response:
        raise HTTPException(400, "Notifikasi tidak valid")

    tx = handle_transaction_status(db, status_response)
    if not tx:
        raise HTTPException(404, "Transaksi tidak ditemukan")
        
    return {"status": "ok"}

@app.get("/payment/status/{order_id}", tags=["Payment"])
async def get_payment_status(order_id: str, db: Session = Depends(get_db)) -> Any:
    # 1. Check local DB first
    tx = db.query(models.Transaction).filter(models.Transaction.order_id == order_id).first()
    if not tx:
        raise HTTPException(404, "Transaksi tidak ditemukan")

    # 2. If pending, sync with Midtrans
    if tx.status == "pending":
        status_response = midtrans_helper.get_status(order_id)
        if status_response:
            tx = handle_transaction_status(db, status_response)

    return {
        "order_id": tx.order_id if tx else order_id,
        "status":   tx.status if tx else "not_found",
        "plan":     tx.plan_tier if tx else "free",
        "amount":   tx.amount if tx else 0
    }
