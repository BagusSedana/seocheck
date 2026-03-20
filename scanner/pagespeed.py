from __future__ import annotations
import httpx
import os
from typing import Dict, Any, Optional

API_KEY = os.getenv("PAGESPEED_API_KEY", "")

async def get_pagespeed(url: str) -> Optional[Dict[str, Any]]:
    if not url.startswith("http"):
        url = "https://" + url

    results: Dict[str, Any] = {}

    for strategy in ["mobile", "desktop"]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                    params={"url": url, "strategy": strategy, "key": API_KEY}
                )
                data = resp.json()

            cats   = data.get("lighthouseResult", {}).get("categories", {})
            audits = data.get("lighthouseResult", {}).get("audits", {})

            def score(key: str) -> int:
                return round((cats.get(key, {}).get("score") or 0) * 100)

            opportunities = []
            diagnostics   = []

            for k, audit in audits.items():
                if audit.get("details", {}).get("type") == "opportunity" and (audit.get("score") or 1) < 0.9:
                    opportunities.append({
                        "title":       str(audit.get("title", "")),
                        "savings":     str(audit.get("displayValue", "")),
                        "description": str(audit.get("description", ""))[:150]
                    })

            for k in ["uses-optimized-images", "uses-webp-images",
                      "render-blocking-resources", "unused-css-rules",
                      "unused-javascript", "uses-text-compression"]:
                if k in audits and (audits[k].get("score") or 1) < 0.9:
                    diagnostics.append({
                        "title": str(audits[k].get("title", "")),
                        "value": str(audits[k].get("displayValue", ""))
                    })

            results[strategy] = {
                "performance_score":    score("performance"),
                "seo_score":            score("seo"),
                "accessibility_score":  score("accessibility"),
                "best_practices_score": score("best-practices"),
                "lcp":         audits.get("largest-contentful-paint", {}).get("displayValue"),
                "cls":         audits.get("cumulative-layout-shift", {}).get("displayValue"),
                "fcp":         audits.get("first-contentful-paint", {}).get("displayValue"),
                "ttfb":        audits.get("server-response-time", {}).get("displayValue"),
                "speed_index": audits.get("speed-index", {}).get("displayValue"),
                "tbt":         audits.get("total-blocking-time", {}).get("displayValue"),
                "opportunities": opportunities[:6],
                "diagnostics":   diagnostics,
                "tap_targets_score": (audits.get("tap-targets", {}).get("score") or 1) * 100,
                "font_size_score":  (audits.get("font-size", {}).get("score") or 1) * 100,
            }
        except Exception as e:
            results[strategy] = {
                "performance_score": 50,
                "error": str(e)
            }

    mobile = results.get("mobile", {})
    return {
        **mobile,
        "mobile":  mobile,
        "desktop": results.get("desktop", {}),
    }
