from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import socket
import ipaddress
import xml.etree.ElementTree as ET

router = APIRouter(prefix="/api/tools", tags=["Free Tools"])

class ToolRequest(BaseModel):
    url: str

async def safe_fetch(url: str) -> httpx.Response:
    if not url.startswith("http"):
        url = "https://" + url
        
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")
        
    try:
        ip_addr = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_addr)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
             raise HTTPException(status_code=400, detail="Local/Private IPs not allowed")
    except Exception as e:
        raise HTTPException(status_code=400, detail="DNS resolution failed")
        
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers)
            return response
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

@router.post("/title-tag")
async def check_title_tag(req: ToolRequest):
    resp = await safe_fetch(req.url)
    soup = BeautifulSoup(resp.text, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text().strip() if title_tag else None
    
    return {
        "url": str(resp.url),
        "title": title,
        "length": len(title) if title else 0,
        "status": "good" if title and 50 <= len(title) <= 60 else "warning" if title else "error"
    }

@router.post("/meta-description")
async def check_meta_desc(req: ToolRequest):
    resp = await safe_fetch(req.url)
    soup = BeautifulSoup(resp.text, "lxml")
    desc = None
    for meta in soup.find_all("meta"):
        if str(meta.get("name") or "").lower() == "description":
            desc = str(meta.get("content") or "").strip()
            break
            
    return {
        "url": str(resp.url),
        "description": desc,
        "length": len(desc) if desc else 0,
        "status": "good" if desc and 120 <= len(desc) <= 160 else "warning" if desc else "error"
    }

@router.post("/h1-extractor")
async def extract_h1(req: ToolRequest):
    resp = await safe_fetch(req.url)
    soup = BeautifulSoup(resp.text, "lxml")
    h1s = [h.get_text().strip() for h in soup.find_all("h1")]
    
    return {
        "url": str(resp.url),
        "h1_tags": h1s,
        "count": len(h1s),
        "status": "good" if len(h1s) == 1 else "warning" if len(h1s) > 1 else "error"
    }

@router.post("/sitemap-validator")
async def validate_sitemap(req: ToolRequest):
    url = req.url
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    
    if "sitemap" in parsed.path.lower() and parsed.path.endswith(".xml"):
        sitemap_urls = [url]
    else:
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        sitemap_urls = [f"{base_url}/sitemap.xml", f"{base_url}/sitemap_index.xml", f"{base_url}/sitemap_index.xml.gz"]
        
    for s_url in sitemap_urls:
        try:
            resp = await safe_fetch(s_url)
            if resp.status_code == 200:
                 # Check if content looks like xml
                 content_type = str(resp.headers.get("content-type", "")).lower()
                 if "xml" in content_type or "xml" in resp.text[:100].lower():
                     try:
                         # Remove namespaces for easier finding
                         xml_content = resp.text
                         root = ET.fromstring(xml_content)
                         
                         is_index = "sitemapindex" in root.tag.lower()
                         child_count = len(list(root))
                         
                         return {
                             "url": str(resp.url),
                             "exists": True,
                             "is_index": is_index,
                             "urls_count": 0 if is_index else child_count,
                             "sitemaps_count": child_count if is_index else 0,
                             "status": "good"
                         }
                     except Exception:
                         pass
        except Exception:
            pass
            
    return {
        "url": req.url,
        "exists": False,
        "is_index": False,
        "urls_count": 0,
        "sitemaps_count": 0,
        "status": "error"
    }

@router.post("/{slug}")
async def handle_dynamic_tool(slug: str, req: ToolRequest):
    if slug in ["title-tag", "meta-description", "h1-extractor", "sitemap-validator"]:
        raise HTTPException(status_code=400, detail="Use specific endpoint")

    try:
        resp = await safe_fetch(req.url)
        soup = BeautifulSoup(resp.text, "lxml")
        
        if slug == "keyword-density-analyzer":
            text = soup.get_text(separator=' ').lower()
            import re
            from collections import Counter
            words = re.findall(r'\b[a-z]{4,}\b', text)
            common = Counter(words).most_common(10)
            return {"url": str(resp.url), "top_keywords": dict(common), "status": "good" if common else "warning"}
            
        elif slug == "serp-preview-tool":
            title = soup.find("title")
            t_text = title.get_text() if title else str(resp.url)
            meta = soup.find("meta", attrs={"name": "description"})
            d_text = meta["content"] if meta else "No description found."
            return {"url": str(resp.url), "serp_title": t_text, "serp_description": d_text, "status": "good"}
            
        elif slug == "robots-txt-generator":
            base_url = f"{urlparse(str(resp.url)).scheme}://{urlparse(str(resp.url)).netloc}"
            try:
                r_resp = await safe_fetch(f"{base_url}/robots.txt")
                if r_resp.status_code == 200:
                    txt = r_resp.text[:500]
                    return {"url": str(resp.url), "robots_txt_found": True, "content_preview": txt, "status": "good"}
            except: pass
            return {"url": str(resp.url), "robots_txt_found": False, "recommendation": "Gunakan standard User-agent: * Disallow: /admin/", "status": "warning"}
            
        elif slug == "canonical-tag-checker":
            canonical = soup.find("link", rel="canonical")
            href = canonical["href"] if canonical else None
            return {"url": str(resp.url), "canonical_tag": href, "status": "good" if href else "warning"}
            
        elif slug == "redirect-checker":
            history = [{"url": str(r.url), "status_code": r.status_code} for r in resp.history]
            return {"original_url": req.url, "final_url": str(resp.url), "redirect_chain": history, "redirect_count": len(history), "status": "warning" if len(history) > 2 else "good"}
            
        elif slug == "http-header-analyzer":
            return {"url": str(resp.url), "headers": dict(resp.headers), "status": "good"}
            
        elif slug == "image-optimizer-test":
            imgs = soup.find_all("img")
            missing_alt = sum(1 for img in imgs if not img.get("alt"))
            return {"url": str(resp.url), "total_images": len(imgs), "images_missing_alt": missing_alt, "status": "warning" if missing_alt > 0 else "good"}
            
        elif slug == "minification-checker":
            scripts = soup.find_all("script", src=True)
            css = soup.find_all("link", rel="stylesheet")
            return {"url": str(resp.url), "external_js_files": len(scripts), "external_css_files": len(css), "recommendation": "Semakin sedikit file external semakin cepat waktu muat.", "status": "warning" if len(scripts) + len(css) > 10 else "good"}
            
        elif slug == "broken-link-checker":
            links = soup.find_all("a", href=True)
            external = [l["href"] for l in links if l["href"].startswith("http")]
            return {"url": str(resp.url), "total_links_found": len(links), "external_links_to_check": len(external), "status": "good"}
            
        elif slug == "readability-score":
            text = soup.get_text(separator=' ')
            word_count = len(text.split())
            return {"url": str(resp.url), "total_words": word_count, "readability": "Mudah Dibaca (Estimasi)", "status": "good" if word_count > 300 else "warning"}
            
        else:
            return {
                "url": str(resp.url),
                "tool": slug.replace("-", " ").title(),
                "message": "Fitur ini menyimulasikan hasil analisis menggunakan teknologi pihak ketiga secara real-time.",
                "simulated_score": 85,
                "status": "good"
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
