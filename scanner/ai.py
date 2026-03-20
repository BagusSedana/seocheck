from __future__ import annotations
import google.generativeai as genai
import json
import os
from typing import Dict, Any, Optional, List

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

async def full_analysis(
    domain: str,
    scores: Dict[str, Any],
    issues: List[Dict[str, str]],
    crawl: Dict[str, Any],
    pagespeed: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:

    critical = [i for i in issues if i.get("severity") == "critical"]
    warnings = [i for i in issues if i.get("severity") == "warning"]

    critical_text = "\n".join([f"- {i['issue']}" for i in critical]) or "Tidak ada"
    warning_text  = "\n".join([f"- {i['issue']}" for i in warnings[:5]]) or "Tidak ada"

    page_info = f"""
Title: {crawl.get('title') or 'Tidak ada'}
Meta: {crawl.get('meta_description') or 'Tidak ada'}
H1: {', '.join(crawl.get('h1_tags', [])[:2]) or 'Tidak ada'}
Kata: {crawl.get('word_count', 0)}
Kontak: {'Ada' if crawl.get('has_contact_info') else 'Tidak ada'}
Schema: {', '.join(crawl.get('schema_types', [])) or 'Tidak ada'}
Social links: {len(crawl.get('social_media_links', []))} platform
"""

    ps_info = ""
    if pagespeed:
        ps_info = f"""
Mobile PageSpeed: {pagespeed.get('performance_score', 'N/A')}/100
LCP: {pagespeed.get('lcp', 'N/A')}
CLS: {pagespeed.get('cls', 'N/A')}
"""

    prompt = f"""
Kamu adalah konsultan SEO senior dengan 10 tahun pengalaman menangani website UMKM dan bisnis lokal Indonesia.

WEBSITE: {domain}
TOTAL SCORE: {scores.get('total_score', 0)}/100
SEO: {scores.get('seo', 0)} | Technical: {scores.get('technical', 0)} | Content: {scores.get('content', 0)} | Performance: {scores.get('performance', 0)} | Local SEO: {scores.get('local', 0)}

INFORMASI HALAMAN:
{page_info}

PERFORMANCE:
{ps_info}

MASALAH KRITIS:
{critical_text}

PERINGATAN:
{warning_text}

KONTEN PREVIEW:
{str(crawl.get('body_text_preview', ''))[:600]}

Berikan analisis dalam format JSON berikut (jawab HANYA JSON valid, tanpa markdown):
{{
  "executive_summary": "Ringkasan 3-4 kalimat, bahasa Indonesia santai tapi profesional, seperti konsultan berbicara ke owner bisnis",
  "grade": "A/B/C/D/F",
  "grade_reason": "Alasan singkat nilai ini",
  "top_3_priorities": [
    {{"rank": 1, "action": "...", "expected_impact": "...", "difficulty": "mudah/sedang/sulit", "time_estimate": "..."}},
    {{"rank": 2, "action": "...", "expected_impact": "...", "difficulty": "...", "time_estimate": "..."}},
    {{"rank": 3, "action": "...", "expected_impact": "...", "difficulty": "...", "time_estimate": "..."}}
  ],
  "content_analysis": "Analisis kualitas konten, apakah sudah menjawab kebutuhan pengunjung",
  "local_seo_assessment": "Seberapa siap website ini untuk local search Indonesia",
  "quick_wins": ["hal yang bisa dilakukan dalam 1 hari", "hal kedua", "hal ketiga"],
  "potential_traffic_impact": "Estimasi potensi peningkatan traffic jika semua issue diselesaikan",
  "competitive_warning": "Kelemahan kompetitif utama yang perlu diperhatikan"
}}
"""

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {
            "executive_summary": f"Website {domain} memiliki beberapa area yang perlu dioptimalkan.",
            "grade": "C",
            "grade_reason": "AI analysis sementara tidak tersedia",
            "top_3_priorities": [],
            "content_analysis": "Tidak tersedia",
            "local_seo_assessment": "Tidak tersedia",
            "quick_wins": [],
            "potential_traffic_impact": "Tidak tersedia",
            "competitive_warning": "Tidak tersedia",
            "error": str(e)
        }
