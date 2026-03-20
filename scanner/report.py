from __future__ import annotations
import os
from typing import Dict, Any, Optional, List

def build_report(
    domain: str,
    crawl: Dict[str, Any],
    rule_result: Dict[str, Any],
    pagespeed: Optional[Dict[str, Any]],
    ai_analysis: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:

    total  = float(rule_result.get("total_score") or 0)
    scores = dict(rule_result.get("scores") or {})

    if total >= 85:
        status, color, badge = "Sehat 🟢", "green", "A"
    elif total >= 70:
        status, color, badge = "Cukup Baik 🟡", "yellow", "B"
    elif total >= 55:
        status, color, badge = "Perlu Perhatian 🟠", "orange", "C"
    elif total >= 40:
        status, color, badge = "Butuh Perbaikan 🔴", "red", "D"
    else:
        status, color, badge = "Kritis — Segera Perbaiki 🚨", "darkred", "F"

    severity_order: Dict[str, int] = {"critical": 0, "warning": 1, "info": 2}
    all_issues: List[Dict[str, str]] = list(rule_result.get("issues") or [])
    sorted_issues = sorted(all_issues, key=lambda x: severity_order.get(x.get("severity", "info"), 3))

    critical = [i for i in sorted_issues if i.get("severity") == "critical"]
    warnings = [i for i in sorted_issues if i.get("severity") == "warning"]
    info     = [i for i in sorted_issues if i.get("severity") == "info"]

    ps = pagespeed or {}
    ai = ai_analysis or {}

    wa_number  = os.getenv("WHATSAPP_NUMBER", "6281234567890")
    app_name   = os.getenv("APP_NAME", "SEO Scanner by Bang Bisnis")

    return {
        "meta": {
            "domain":      domain,
            "url_scanned": str(crawl.get("url") or ""),
            "final_url":   str(crawl.get("final_url") or ""),
            "status_code": crawl.get("status_code"),
            "is_https":    bool(crawl.get("is_https")),
            "scanned_at":  None,
            "app_name":    app_name,
        },
        "overview": {
            "total_score": total,
            "grade":       str(ai.get("grade") or badge),
            "status":      status,
            "status_color": color,
            "executive_summary": str(
                ai.get("executive_summary") or _auto_summary(total, domain)
            ),
            "issue_count": dict(rule_result.get("issue_count") or {}),
        },
        "scores": {
            "total":       total,
            "seo":         float(scores.get("seo") or 0),
            "technical":   float(scores.get("technical") or 0),
            "content":     float(scores.get("content") or 0),
            "performance": float(scores.get("performance") or 0),
            "local_seo":   float(scores.get("local") or 0),
            "social":      float(scores.get("social") or 0),
        },
        "page_info": {
            "title":              crawl.get("title"),
            "title_length":       crawl.get("title_length"),
            "meta_description":   crawl.get("meta_description"),
            "meta_desc_length":   crawl.get("meta_description_length"),
            "h1_tags":            list(crawl.get("h1_tags") or [])[:3],
            "h2_tags":            list(crawl.get("h2_tags") or [])[:5],
            "canonical":          crawl.get("canonical"),
            "lang":               crawl.get("lang_attribute"),
            "has_viewport":       bool(crawl.get("viewport_meta")),
            "has_robots_txt":     bool(crawl.get("has_robots_txt")),
            "has_sitemap":        bool(crawl.get("has_sitemap")),
            "has_schema":         bool(crawl.get("schema_types")),
            "schema_types":       list(crawl.get("schema_types") or []),
            "word_count":         int(crawl.get("word_count") or 0),
            "paragraph_count":    int(crawl.get("paragraph_count") or 0),
            "total_images":       int(crawl.get("total_images") or 0),
            "images_without_alt": int(crawl.get("images_without_alt") or 0),
            "internal_links":     int(crawl.get("internal_links") or 0),
            "external_links":     int(crawl.get("external_links") or 0),
            "has_contact_info":   bool(crawl.get("has_contact_info")),
            "phone_numbers":      list(crawl.get("phone_numbers") or []),
            "email_addresses":    list(crawl.get("email_addresses") or []),
            "address_found":      bool(crawl.get("address_found")),
            "social_media_links": list(crawl.get("social_media_links") or []),
            "google_maps":        bool(crawl.get("google_maps_embed")),
            "og_complete":        bool(crawl.get("og_title") and crawl.get("og_image")),
            "twitter_card":       crawl.get("twitter_card"),
            "favicon":            bool(crawl.get("favicon")),
            "redirect_count":     int(crawl.get("redirect_count") or 0),
            "next_gen_images":    int(crawl.get("next_gen_images") or 0),
            "security_headers":   len(crawl.get("security_headers") or {}),
            "has_main_tag":       (crawl.get("semantic_tags") or {}).get("main", 0) > 0,
            "trust_pages":        crawl.get("trust_pages") or {},
            "compression":        crawl.get("compression"),
            "resource_hints":     len(crawl.get("resource_hints") or []),
            "keyword_density":    crawl.get("keyword_density", {}),
            "tap_targets_score":  ps.get("tap_targets_score"),
            "font_size_score":    ps.get("font_size_score"),
        },
        "performance": {
            "mobile": {
                "score":        ps.get("performance_score"),
                "lcp":          ps.get("lcp"),
                "cls":          ps.get("cls"),
                "fcp":          ps.get("fcp"),
                "ttfb":         ps.get("ttfb"),
                "tbt":          ps.get("tbt"),
                "speed_index":  ps.get("speed_index"),
                "opportunities": list(ps.get("opportunities") or []),
                "diagnostics":  list(ps.get("diagnostics") or []),
            },
            "desktop": dict(ps.get("desktop") or {}),
        },
        "issues": {
            "all":      sorted_issues,
            "critical": critical,
            "warnings": warnings,
            "info":     info,
        },
        "action_plan": {
            "fix_now":       critical[:4],
            "fix_this_week": warnings[:5],
            "fix_later":     info[:4],
            "ai_priorities": list(ai.get("top_3_priorities") or []),
            "quick_wins":    list(ai.get("quick_wins") or []),
        },
        "ai_insights": {
            "available":                bool(ai_analysis),
            "grade_reason":             ai.get("grade_reason"),
            "content_analysis":         ai.get("content_analysis"),
            "local_seo_assessment":     ai.get("local_seo_assessment"),
            "potential_traffic_impact": ai.get("potential_traffic_impact"),
            "competitive_warning":      ai.get("competitive_warning"),
        },
        "cta": {
            "upgrade_headline": "Ingin audit lebih dalam untuk semua halaman website kamu?",
            "upgrade_sub":      "Pro plan: multi-page audit, PDF report, dan AI insight lengkap.",
            "service_headline": "Tidak mau ribet? Tim Bang Bisnis bisa bantu perbaiki semua issue ini.",
            "service_sub":      "Dari fix title/meta sampai implementasi schema, kami kerjakan untuk kamu.",
            "whatsapp_url":     f"https://wa.me/{wa_number}?text=Halo, saya mau konsultasi SEO website saya: {domain}",
            "upgrade_url":      "/pricing",
            "service_packages": [
                {"name": "Audit Kilat",     "price": "Rp499.000",    "desc": "Audit manual + roadmap + konsultasi WA"},
                {"name": "SEO Fix Starter", "price": "Rp1.500.000",  "desc": "Fix title/meta/H1/sitemap/robots/schema dasar"},
                {"name": "Local Growth",    "price": "Rp3.000.000",  "desc": "Full starter + local SEO + keyword targeting"},
            ]
        }
    }

def _auto_summary(score: float, domain: str) -> str:
    if score >= 85:
        return f"Website {domain} sudah dalam kondisi SEO yang baik. Ada beberapa area kecil yang bisa dioptimalkan."
    elif score >= 70:
        return f"Website {domain} punya fondasi SEO yang cukup, tapi masih ada beberapa hal penting yang perlu dibenahi."
    elif score >= 55:
        return f"Website {domain} membutuhkan perhatian di beberapa area SEO penting. Perbaikan yang tepat bisa berdampak signifikan."
    else:
        return f"Website {domain} memiliki sejumlah masalah SEO serius yang menghambat kemampuannya muncul di Google."
