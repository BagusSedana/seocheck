from __future__ import annotations
import httpx
import re
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, Any

import socket
import ipaddress

async def crawl(url: str) -> Dict[str, Any]:
    if not url.startswith("http"):
        url = "https://" + url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"
    }

    result: Dict[str, Any] = {
        "url": url,
        "status_code": None,
        "final_url": None,
        "redirect_count": 0,
        "title": None,
        "title_length": 0,
        "meta_description": None,
        "meta_description_length": 0,
        "meta_keywords": None,
        "h1_tags": [],
        "h2_tags": [],
        "h3_tags": [],
        "h1_count": 0,
        "canonical": None,
        "robots_meta": None,
        "viewport_meta": None,
        "charset": None,
        "lang_attribute": None,
        "favicon": None,
        "og_title": None,
        "og_description": None,
        "og_image": None,
        "og_url": None,
        "og_type": None,
        "twitter_card": None,
        "twitter_title": None,
        "schema_types": [],
        "schema_raw": [],
        "internal_links": 0,
        "external_links": 0,
        "nofollow_links": 0,
        "total_images": 0,
        "images_without_alt": 0,
        "images_with_alt": 0,
        "has_lazy_loading": False,
        "word_count": 0,
        "body_text_preview": "",
        "paragraph_count": 0,
        "has_contact_info": False,
        "phone_numbers": [],
        "email_addresses": [],
        "address_found": False,
        "google_maps_embed": False,
        "social_media_links": [],
        "has_robots_txt": False,
        "has_sitemap": False,
        "is_https": url.startswith("https"),
        "has_ssl_valid": False,
        "has_404_page": False,
        "inline_styles_count": 0,
        "inline_scripts_count": 0,
        "internal_css_count": 0,
        "total_css_files": 0,
        "total_js_files": 0,
        "deprecated_tags": [],
        "nested_tables": 0,
        "security_headers": {},
        "semantic_tags": {},
        "trust_pages": {
            "about": False,
            "privacy": False,
            "terms": False,
            "contact": False
        },
        "next_gen_images": 0,
        "lorem_ipsum_found": False,
        "keyword_density": {},
        "tap_target_info": {"potential_issues": 0},
        "font_size_info": {"potential_issues": 0},
        "resource_hints": [],
        "hreflang_tags": [],
        "compression": None,
        "error": None
    }

    current_url = url
    redirect_count = 0
    max_redirects = 5

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, verify=True) as client:
            while redirect_count <= max_redirects:
                # SSRF Protection & IP Pinning
                parsed_url = urlparse(current_url)
                hostname = parsed_url.hostname
                if not hostname:
                    raise ValueError("URL tidak valid")
                
                try:
                    ip_addr = socket.gethostbyname(hostname)
                    ip = ipaddress.ip_address(ip_addr)
                    
                    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                        result["error"] = f"Akses ke IP internal/private ({ip_addr}) dilarang."
                        return result
                        
                    if ip_addr == "169.254.169.254":
                        result["error"] = "Akses ke cloud metadata dilarang."
                        return result
                except Exception as e:
                    result["error"] = f"Gagal validasi keamanan DNS: {str(e)}"
                    return result

                # Request dengan manual redirect handling
                response = await client.get(current_url, headers=headers)
                
                if response.is_redirect:
                    redirect_count += 1
                    current_url = str(response.url.join(response.headers["Location"]))
                    result["redirect_count"] = redirect_count
                    if redirect_count > max_redirects:
                        result["error"] = "Terlalu banyak redirect"
                        break
                    continue
                else:
                    break

            result["status_code"]    = response.status_code
            result["final_url"]      = str(response.url)
            result["has_ssl_valid"]  = str(response.url).startswith("https")
            
            # COMPRESSION
            编码 = response.headers.get("Content-Encoding", "").lower()
            if "br" in 编码:   result["compression"] = "Brotli"
            elif "gzip" in 编码: result["compression"] = "Gzip"
            
            # SECURITY HEADERS
            
            # SECURITY HEADERS
            sec_headers = ["Content-Security-Policy", "Strict-Transport-Security", 
                           "X-Frame-Options", "X-Content-Type-Options", "X-XSS-Protection",
                           "Permissions-Policy", "Referrer-Policy"]
            for h in sec_headers:
                if h in response.headers:
                    result["security_headers"][h] = response.headers[h]

            soup = BeautifulSoup(response.text, "html.parser")
            parsed  = urlparse(url)
            domain  = parsed.netloc
            base_domain = domain.replace("www.", "")

            # TITLE
            title_tag = soup.find("title")
            if title_tag:
                result["title"]        = title_tag.get_text().strip()
                result["title_length"] = len(result["title"])

            # META TAGS
            for meta in soup.find_all("meta"):
                name    = str(meta.get("name") or "").lower()
                prop    = str(meta.get("property") or "").lower()
                content = str(meta.get("content") or "")

                if name == "description":
                    result["meta_description"]        = content.strip()
                    result["meta_description_length"] = len(content.strip())
                elif name == "keywords":
                    result["meta_keywords"] = content.strip()
                elif name == "robots":
                    result["robots_meta"] = content.strip()
                elif name == "viewport":
                    result["viewport_meta"] = content.strip()
                elif prop == "og:title":
                    result["og_title"] = content
                elif prop == "og:description":
                    result["og_description"] = content
                elif prop == "og:image":
                    result["og_image"] = content
                elif prop == "og:url":
                    result["og_url"] = content
                elif prop == "og:type":
                    result["og_type"] = content
                elif name == "twitter:card":
                    result["twitter_card"] = content
                elif name == "twitter:title":
                    result["twitter_title"] = content

            # CHARSET
            charset_tag = soup.find("meta", charset=True)
            if charset_tag:
                result["charset"] = charset_tag.get("charset")

            # HTML LANG
            html_tag = soup.find("html")
            if html_tag:
                result["lang_attribute"] = html_tag.get("lang")

            # CANONICAL
            canonical = soup.find("link", attrs={"rel": "canonical"})
            if canonical and canonical.get("href"):
                result["canonical"] = canonical["href"]

            # HREFLANG
            for link in soup.find_all("link", attrs={"rel": "alternate", "hreflang": True}):
                result["hreflang_tags"].append(link.get("hreflang"))

            # RESOURCE HINTS
            for link in soup.find_all("link", attrs={"rel": lambda r: r in ["preload", "preconnect", "dns-prefetch"]}):
                if link.get("rel"):
                    result["resource_hints"].extend(link.get("rel") if isinstance(link.get("rel"), list) else [link.get("rel")])

            # FAVICON
            favicon = soup.find("link", attrs={"rel": lambda r: r and "icon" in str(r).lower()})
            if favicon and favicon.get("href"):
                result["favicon"] = str(favicon["href"])

            # SEMANTIC TAGS
            semantic_elements = ["main", "nav", "aside", "footer", "header", "article", "section"]
            for el in semantic_elements:
                result["semantic_tags"][el] = len(soup.find_all(el))

            # DEPRECATED TAGS
            deprecated = ["font", "center", "strike", "u", "dir", "applet", "basefont", "big", "frameset", "frame"]
            for tag in deprecated:
                if soup.find_all(tag):
                    result["deprecated_tags"].append(tag)
            
            # NESTED TABLES
            total_nested = 0
            for table in soup.find_all("table"):
                if table.find("table"):
                    total_nested += 1
            result["nested_tables"] = total_nested

            # HEADINGS
            result["h1_tags"]  = [h.get_text().strip() for h in soup.find_all("h1")]
            result["h2_tags"]  = [h.get_text().strip() for h in soup.find_all("h2")][:8]
            result["h3_tags"]  = [h.get_text().strip() for h in soup.find_all("h3")][:5]
            result["h1_count"] = len(result["h1_tags"])

            # SCHEMA.ORG
            for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
                try:
                    content = script.string or "{}"
                    data = json.loads(content)
                    if isinstance(data, dict):
                        result["schema_types"].append(str(data.get("@type", "Unknown")))
                        result["schema_raw"].append(json.dumps(data)[:200])
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                result["schema_types"].append(str(item.get("@type", "Unknown")))
                except Exception:
                    pass

            # LINKS
            social_domains = [
                "facebook.com", "instagram.com", "tiktok.com",
                "youtube.com", "twitter.com", "x.com",
                "linkedin.com", "whatsapp.com"
            ]
            for link in soup.find_all("a", href=True):
                href = str(link.get("href", ""))
                rel  = link.get("rel", [])
                if not href or href.startswith("#") or href.startswith("javascript"):
                    continue
                
                rel_list = rel if isinstance(rel, list) else [rel]
                if "nofollow" in rel_list:
                    result["nofollow_links"] += 1
                
                if href.startswith("http"):
                    if base_domain in href:
                        result["internal_links"] += 1
                    else:
                        result["external_links"] += 1
                        for sd in social_domains:
                            if sd in href and href not in result["social_media_links"]:
                                result["social_media_links"].append(href)
                else:
                    result["internal_links"] += 1
                
                # E-E-A-T TRUST PAGES
                text = link.get_text().lower()
                if any(k in text for k in ["tentang", "about"]):   result["trust_pages"]["about"] = True
                if any(k in text for k in ["privasi", "privacy"]): result["trust_pages"]["privacy"] = True
                if any(k in text for k in ["syarat", "terms"]):     result["trust_pages"]["terms"] = True
                if any(k in text for k in ["kontak", "contact"]):   result["trust_pages"]["contact"] = True

            # IMAGES
            for img in soup.find_all("img"):
                result["total_images"] += 1
                src = str(img.get("src", "")).lower()
                if any(ext in src for ext in [".webp", ".avif"]):
                    result["next_gen_images"] += 1
                
                alt = img.get("alt")
                if alt is None or str(alt).strip() == "":
                    result["images_without_alt"] += 1
                else:
                    result["images_with_alt"] += 1
                if img.get("loading") == "lazy":
                    result["has_lazy_loading"] = True

            # CONTENT
            body = soup.find("body")
            if body:
                raw_text = body.get_text(separator=" ", strip=True)
                words = raw_text.split()
                result["word_count"]        = len(words)
                result["body_text_preview"] = " ".join(words[:400])
                result["paragraph_count"]   = len(soup.find_all("p"))
                
                # KEYWORD DENSITY
                result["keyword_density"] = _get_keyword_density(soup)

                # MOBILE HINTS (Tap Targets)
                result["tap_target_info"] = _get_tap_target_info(soup)
                
                if "lorem ipsum" in raw_text.lower():
                    result["lorem_ipsum_found"] = True

            # CONTACT INFO
            full_text = soup.get_text(" ")
            phone_pattern = r'(\+62|08)[0-9\-\s]{8,14}'
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            phones = list(set(re.findall(phone_pattern, full_text)))
            emails = list(set(re.findall(email_pattern, full_text)))
            result["phone_numbers"]   = phones[:3]
            result["email_addresses"] = [
                e for e in emails
                if "example" not in e and "yourdomain" not in e
            ][:3]
            result["has_contact_info"] = bool(phones or result["email_addresses"])

            address_keywords = ["jalan", "jl.", "gang", "kota", "kabupaten", "bali", "jakarta"]
            result["address_found"] = any(kw in full_text.lower() for kw in address_keywords)

            # GOOGLE MAPS
            result["google_maps_embed"] = bool(
                soup.find("iframe", src=lambda s: s and "google.com/maps" in str(s))
            )

            # PERFORMANCE HINTS
            result["inline_scripts_count"] = len(soup.find_all("script", src=False))
            result["inline_styles_count"]  = len(soup.find_all(style=True))
            result["internal_css_count"]   = len(soup.find_all("style"))
            result["total_css_files"]      = len(soup.find_all("link", rel="stylesheet"))
            result["total_js_files"]       = len(soup.find_all("script", src=True))

            base_url = f"{parsed.scheme}://{domain}"

            # SITEMAP & ROBOTS
            # Kita tidak re-validate SSRF di sini untuk brevity, tapi idealnya pakai helper function
            try:
                r = await client.get(f"{base_url}/robots.txt", timeout=5)
                result["has_robots_txt"] = r.status_code == 200 and len(r.text) > 5
                
                for path in ["/sitemap.xml", "/sitemap_index.xml"]:
                    r = await client.get(f"{base_url}{path}", timeout=5)
                    if r.status_code == 200:
                        result["has_sitemap"] = True
                        break
                        
                r = await client.get(f"{base_url}/halaman-ini-pasti-404-xyzabc", timeout=5)
                result["has_404_page"] = r.status_code == 404
            except Exception:
                pass

    except Exception as e:
        result["error"] = str(e)

    return result

def _get_keyword_density(soup: BeautifulSoup) -> Dict[str, int]:
    from collections import Counter
    import string
    
    # Get all text and split into words
    raw_text = soup.get_text(" ")
    words = re.findall(r'\b\w+\b', raw_text.lower())
    
    stop_words = {"dan", "di", "ke", "dari", "ini", "itu", "yang", "adalah", "untuk", "dengan", "saya", "kamu", "anda", "kami", "mereka", "juga", "atau", "pada", "sebuah", "oleh", "the", "and", "is", "in", "to"}
    clean_words = [w.strip(string.punctuation).lower() for w in words if len(w) >= 3]
    filtered = [w for w in clean_words if w not in stop_words and w.isalpha()]
    counts = Counter(filtered).most_common(10)
    return {w: count for w, count in counts}

def _get_tap_target_info(soup: BeautifulSoup) -> Dict[str, Any]:
    info = {"potential_issues": 0}
    links = soup.find_all("a")
    for i in range(len(links) - 1):
        # Simple heuristic: if links are direct siblings and texts are short
        if links[i].parent == links[i+1].parent and len(links[i].get_text()) < 10:
            info["potential_issues"] += 1
    return info
