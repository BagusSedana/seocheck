from __future__ import annotations
from typing import Dict, List, Any, Optional

def analyze(crawl: Dict[str, Any], pagespeed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    score: Dict[str, float] = {
        "seo":         100.0,
        "technical":   100.0,
        "content":     100.0,
        "social":      100.0,
        "local":       100.0,
        "performance": float((pagespeed or {}).get("performance_score") or 70)
    }

    def add(
        category: str,
        severity: str,
        issue: str,
        why: str,
        fix: str,
        penalty_key: Optional[str] = None,
        penalty: float = 0
    ) -> None:
        issues.append({
            "category": category,
            "severity": severity,
            "issue": issue,
            "why": why,
            "fix": fix
        })
        if penalty_key and penalty:
            score[penalty_key] = max(0.0, score[penalty_key] - penalty)

    # ── TITLE ──────────────────────────────────
    title = crawl.get("title") or ""
    tlen  = int(crawl.get("title_length") or 0)
    if not title:
        add("SEO Dasar", "critical",
            "Title tag tidak ditemukan",
            "Title adalah elemen paling penting untuk ranking Google. Tanpa title, Google tidak tahu topik halaman.",
            "Tambahkan <title> unik di setiap halaman, 50–60 karakter, keyword utama di depan.",
            "seo", 20)
    elif tlen < 30:
        add("SEO Dasar", "warning",
            f"Title terlalu pendek ({tlen} karakter)",
            "Title singkat tidak memanfaatkan ruang keyword dan terlihat kurang informatif.",
            f"Perluas title menjadi 50–60 karakter. Saat ini: '{title}'",
            "seo", 8)
    elif tlen > 65:
        add("SEO Dasar", "warning",
            f"Title terlalu panjang ({tlen} karakter) — akan dipotong Google",
            "Google memotong title di sekitar 60 karakter. Bagian yang dipotong tidak terlihat user.",
            f"Persingkat menjadi maksimal 60 karakter. Saat ini: '{title[:55]}...'",
            "seo", 5)

    # ── META DESCRIPTION ───────────────────────
    meta = crawl.get("meta_description") or ""
    mlen = int(crawl.get("meta_description_length") or 0)
    if not meta:
        add("SEO Dasar", "critical",
            "Meta description tidak ada",
            "Meta description tampil sebagai deskripsi di hasil Google. Tanpanya, Google ambil teks acak.",
            "Tambahkan meta description 120–155 karakter yang menjelaskan value halaman.",
            "seo", 15)
    elif mlen < 70:
        add("SEO Dasar", "warning",
            f"Meta description terlalu pendek ({mlen} karakter)",
            "Deskripsi singkat kurang persuasif mengajak user klik.",
            "Tulis deskripsi minimal 120 karakter dengan keyword.",
            "seo", 7)
    elif mlen > 160:
        add("SEO Dasar", "warning",
            f"Meta description terlalu panjang ({mlen} karakter)",
            "Google memotong di ~155 karakter, pesan utama bisa hilang.",
            "Persingkat menjadi 120–155 karakter.",
            "seo", 4)

    # ── H1 ─────────────────────────────────────
    h1_count = int(crawl.get("h1_count") or 0)
    h1_tags  = list(crawl.get("h1_tags") or [])
    if h1_count == 0:
        add("Struktur Konten", "critical",
            "H1 tidak ditemukan",
            "H1 adalah judul utama halaman. Google menggunakannya sebagai sinyal topik utama.",
            "Tambahkan tepat satu <h1> dengan keyword utama halaman.",
            "content", 15)
    elif h1_count > 1:
        add("Struktur Konten", "warning",
            f"Terlalu banyak H1 ({h1_count} tag ditemukan)",
            "Multiple H1 membingungkan mesin pencari tentang topik utama halaman.",
            f"Pertahankan hanya satu H1. H1 yang ditemukan: {', '.join(h1_tags[:3])}",
            "content", 8)

    h2_tags = list(crawl.get("h2_tags") or [])
    if not h2_tags:
        add("Struktur Konten", "info",
            "Tidak ada H2 ditemukan",
            "H2 membantu struktur konten dan memberikan sinyal topik sekunder ke Google.",
            "Tambahkan H2 sebagai sub-heading untuk memecah konten.",
            "content", 4)

    # ── CANONICAL ──────────────────────────────
    if not crawl.get("canonical"):
        add("SEO Teknikal", "warning",
            "Canonical tag tidak ada",
            "Tanpa canonical, Google bisa anggap variasi URL sebagai duplicate content.",
            "Tambahkan <link rel='canonical' href='URL_UTAMA'> di setiap halaman.",
            "technical", 7)

    # ── HTTPS & SSL ────────────────────────────
    if not crawl.get("is_https"):
        add("Keamanan", "critical",
            "Website tidak menggunakan HTTPS",
            "HTTPS adalah faktor ranking resmi Google. Browser modern tampilkan peringatan untuk HTTP.",
            "Pasang SSL certificate gratis via Let's Encrypt dan redirect semua HTTP ke HTTPS.",
            "technical", 20)
    elif not crawl.get("has_ssl_valid"):
        add("Keamanan", "critical",
            "SSL certificate bermasalah atau expired",
            "SSL tidak valid menyebabkan browser menampilkan error ke pengunjung.",
            "Perbarui SSL certificate segera.",
            "technical", 15)

    # ── VIEWPORT ───────────────────────────────
    if not crawl.get("viewport_meta"):
        add("Mobile SEO", "critical",
            "Viewport meta tag tidak ada — website tidak mobile-friendly",
            "Google pakai mobile-first indexing. Tanpa viewport tag, halaman dianggap tidak responsif.",
            "Tambahkan: <meta name='viewport' content='width=device-width, initial-scale=1'>",
            "technical", 18)

    # ── LANG ATTRIBUTE ─────────────────────────
    if not crawl.get("lang_attribute"):
        add("SEO Teknikal", "info",
            "Atribut lang tidak ditemukan di tag HTML",
            "Atribut lang membantu Google dan screen reader memahami bahasa konten.",
            "Tambahkan lang='id' pada <html> jika konten dalam Bahasa Indonesia.",
            "technical", 3)

    # ── ROBOTS.TXT ─────────────────────────────
    if not crawl.get("has_robots_txt"):
        add("SEO Teknikal", "warning",
            "File robots.txt tidak ditemukan",
            "Robots.txt memberi instruksi ke crawler dan referensi sitemap.",
            "Buat robots.txt di root domain. Contoh:\nUser-agent: *\nAllow: /\nSitemap: https://domain.com/sitemap.xml",
            "technical", 6)

    # ── SITEMAP ────────────────────────────────
    if not crawl.get("has_sitemap"):
        add("SEO Teknikal", "warning",
            "Sitemap XML tidak ditemukan",
            "Sitemap mempercepat crawling dan indexing oleh Google.",
            "Buat sitemap.xml dan submit ke Google Search Console.",
            "technical", 6)

    # ── ROBOTS META NOINDEX ────────────────────
    robots_meta = str(crawl.get("robots_meta") or "").lower()
    if "noindex" in robots_meta:
        add("SEO Teknikal", "critical",
            "Halaman ini di-set NOINDEX — tidak akan muncul di Google",
            "Meta robots noindex mencegah Google mengindeks halaman ini.",
            "Hapus 'noindex' dari meta robots jika ingin halaman terindeks.",
            "technical", 25)

    # ── OPEN GRAPH ─────────────────────────────
    og_complete = crawl.get("og_title") and crawl.get("og_description") and crawl.get("og_image")
    if not og_complete:
        missing = []
        if not crawl.get("og_title"):       missing.append("og:title")
        if not crawl.get("og_description"): missing.append("og:description")
        if not crawl.get("og_image"):       missing.append("og:image")
        add("Social Media", "warning",
            f"Open Graph tidak lengkap — hilang: {', '.join(missing)}",
            "Open Graph mengontrol tampilan link saat dishare di Facebook, WhatsApp, dan sosmed lainnya.",
            "Tambahkan og:title, og:description, dan og:image (min 1200x630px).",
            "social", 10)

    # ── TWITTER CARD ───────────────────────────
    if not crawl.get("twitter_card"):
        add("Social Media", "info",
            "Twitter Card tidak ditemukan",
            "Twitter Card mengontrol tampilan link saat dishare di Twitter/X.",
            "Tambahkan: <meta name='twitter:card' content='summary_large_image'>",
            "social", 4)

    # ── IMAGES ALT ─────────────────────────────
    no_alt = int(crawl.get("images_without_alt") or 0)
    total  = int(crawl.get("total_images") or 0)
    if total > 0 and no_alt > 0:
        pct      = round((no_alt / total) * 100)
        severity = "critical" if pct > 60 else "warning"
        add("SEO Dasar", severity,
            f"{no_alt}/{total} gambar tidak punya alt text ({pct}%)",
            "Alt text membantu Google memahami gambar dan meningkatkan aksesibilitas.",
            "Tambahkan alt text deskriptif pada setiap gambar.",
            "seo", min(12, no_alt * 2))

    # ── INTERNAL LINKS ─────────────────────────
    internal = int(crawl.get("internal_links") or 0)
    if internal == 0:
        add("Struktur Konten", "critical",
            "Tidak ada internal link ditemukan",
            "Internal link membantu crawler menemukan halaman lain dan distribusikan PageRank.",
            "Tambahkan minimal 3–5 internal link ke halaman penting lain.",
            "content", 12)
    elif internal < 3:
        add("Struktur Konten", "warning",
            f"Internal link sangat sedikit (hanya {internal})",
            "Terlalu sedikit internal link menghambat distribusi authority di dalam situs.",
            "Tambahkan lebih banyak internal link yang relevan.",
            "content", 6)

    # ── WORD COUNT ─────────────────────────────
    wc = int(crawl.get("word_count") or 0)
    if wc < 100:
        add("Kualitas Konten", "critical",
            f"Konten sangat tipis — hanya {wc} kata",
            "Google cenderung tidak meranking halaman dengan konten sangat minim.",
            "Tambahkan konten berkualitas minimal 300–500 kata.",
            "content", 15)
    elif wc < 300:
        add("Kualitas Konten", "warning",
            f"Konten cukup tipis ({wc} kata)",
            "Halaman dengan sedikit teks sering kesulitan ranking.",
            "Kembangkan konten menjadi minimal 500 kata.",
            "content", 7)

    # ── KEYWORD DENSITY (NEW) ──────────────────
    kd = crawl.get("keyword_density") or {}
    if kd:
        top_words = list(kd.keys())
        # If no word appears more than 3 times, might be low density
        if max(kd.values()) < 3:
            add("SEO Dasar", "info",
                "Densitas kata kunci rendah",
                "Konten kamu tidak memiliki kata-kata yang cukup dominan untuk membantu Google memahami topik utama.",
                "Pastikan kata kunci utama muncul beberapa kali secara natural di dalam teks.",
                "seo", 3)
        else:
            # Check if title keywords are in top words
            title_words = [w.lower() for w in title.split() if len(w) > 3]
            matches = [w for w in title_words if w in top_words]
            if not matches:
                 add("SEO Dasar", "warning",
                    "Kata kunci di Title tidak dominan di Konten",
                    "Kata kunci yang kamu targetkan di Title tidak banyak muncul di isi halaman.",
                    "Gunakan kata kunci dari Title lebih sering di dalam paragraf konten.",
                    "seo", 5)

    # ── MOBILE USABILITY (NEW) ─────────────────
    # Combine crawler hints and PageSpeed data
    tap_issues = crawl.get("tap_target_info", {}).get("potential_issues", 0)
    ps_tap_score = (pagespeed or {}).get("tap_targets_score", 100)
    
    if ps_tap_score < 90 or tap_issues > 10:
        add("Mobile SEO", "warning",
            f"Tap targets terlalu berdekatan (Score: {int(ps_tap_score)})",
            "Elemen interaktif (link/button) terlalu dekat satu sama lain, menyulitkan pengguna layar sentuh.",
            "Berikan padding atau margin minimal 48px antar elemen yang bisa diklik.",
            "technical", 8)

    font_issues = crawl.get("font_size_info", {}).get("potential_issues", 0)
    ps_font_score = (pagespeed or {}).get("font_size_score", 100)
    
    if ps_font_score < 90:
        add("Mobile SEO", "critical",
            "Ukuran font terlalu kecil untuk mobile",
            "Teks yang terlalu kecil (< 12px) memaksa pengguna 'pinch-to-zoom' untuk membaca.",
            "Gunakan ukuran font minimal 16px untuk teks utama dan pastikan viewport sudah benar.",
            "technical", 10)

    # ── LOCAL SEO ──────────────────────────────
    if not crawl.get("has_contact_info"):
        add("Local SEO", "warning",
            "Informasi kontak tidak ditemukan di halaman",
            "Google menggunakan NAP (Name, Address, Phone) untuk local ranking.",
            "Tambahkan nomor telepon, email, dan alamat di halaman utama atau footer.",
            "local", 15)
    else:
        if not crawl.get("phone_numbers"):
            add("Local SEO", "warning",
                "Nomor telepon tidak terdeteksi",
                "Nomor telepon penting untuk konversi dan local SEO.",
                "Tambahkan nomor telepon yang mudah ditemukan di header atau hero section.",
                "local", 8)
        if not crawl.get("address_found"):
            add("Local SEO", "info",
                "Alamat fisik tidak terdeteksi",
                "Alamat lengkap membantu ranking local SEO dan membangun kepercayaan.",
                "Tambahkan alamat lengkap di footer atau halaman kontak.",
                "local", 5)

    if not crawl.get("google_maps_embed"):
        add("Local SEO", "info",
            "Embed Google Maps tidak ditemukan",
            "Google Maps embed memperkuat local SEO signal.",
            "Tambahkan embed Google Maps dari Google Business Profile kamu.",
            "local", 4)

    if not crawl.get("social_media_links"):
        add("Social Media", "info",
            "Tidak ada link ke media sosial",
            "Link sosmed membangun kepercayaan dan brand presence.",
            "Tambahkan link ke Instagram, Facebook, atau TikTok bisnis kamu.",
            "social", 5)

    # ── FAVICON ────────────────────────────────
    if not crawl.get("favicon"):
        add("Kepercayaan", "info",
            "Favicon tidak ditemukan",
            "Favicon meningkatkan brand recognition di tab browser.",
            "Tambahkan favicon 32x32px di dalam <head>.",
            "social", 3)

    # ── PERFORMANCE ────────────────────────────
    ps = float((pagespeed or {}).get("performance_score") or 70)
    if ps < 50:
        add("Performa", "critical",
            f"Kecepatan website sangat lambat — PageSpeed score: {int(ps)}/100",
            "Google menjadikan kecepatan sebagai faktor ranking. Website lambat tingkatkan bounce rate.",
            "Kompres gambar ke WebP, minify CSS/JS, aktifkan browser caching.",
            "technical", 0)
    elif ps < 70:
        add("Performa", "warning",
            f"Kecepatan website perlu ditingkatkan — PageSpeed score: {int(ps)}/100",
            "Website lambat buat pengunjung pergi sebelum halaman selesai load.",
            "Optimalkan gambar, kurangi render-blocking scripts, aktifkan Gzip/Brotli.",
            "technical", 0)

    if pagespeed:
        lcp_raw = str(pagespeed.get("lcp") or "")
        if lcp_raw:
            try:
                lcp_val = float("".join(c for c in lcp_raw if c.isdigit() or c == "."))
                if lcp_val > 4.0:
                    add("Core Web Vitals", "critical",
                        f"LCP sangat lambat: {lcp_raw} (target < 2.5 detik)",
                        "LCP mengukur waktu loading elemen terbesar. Google target < 2.5 detik.",
                        "Optimalkan gambar hero, preload font, dan kurangi server response time.",
                        "technical", 8)
                elif lcp_val > 2.5:
                    add("Core Web Vitals", "warning",
                        f"LCP perlu dioptimalkan: {lcp_raw}",
                        "LCP > 2.5 detik diklasifikasikan Google sebagai 'Needs Improvement'.",
                        "Kompres gambar hero, pakai WebP/AVIF, dan optimalkan server.",
                        "technical", 4)
            except ValueError:
                pass

    # ── INLINE SCRIPTS ─────────────────────────
    inline_scripts = int(crawl.get("inline_scripts_count") or 0)
    if inline_scripts > 10:
        add("Performa", "info",
            f"Terlalu banyak inline script ({inline_scripts} blok)",
            "Inline scripts berlebihan menghambat rendering dan sulit di-cache.",
            "Pindahkan script ke file eksternal dan load async atau defer.",
            "technical", 4)
            
    # ── COMPRESSION (NEW) ──────────────────────
    if not crawl.get("compression"):
        add("Performa", "warning",
            "Kompresi teks (Gzip/Brotli) tidak aktif",
            "Kompresi mengurangi ukuran file HTML/CSS/JS secara signifikan (sampai 70%).",
            "Aktifkan Gzip atau Brotli di server (Nginx/Apache/Cloudflare).",
            "performance", 10)

    # ── RESOURCE HINTS (NEW) ───────────────────
    if not crawl.get("resource_hints"):
        add("Performa", "info",
            "Tidak ada Resource Hints (preload/preconnect)",
            "Resource hints memberitahu browser untuk mulai mendownload file penting lebih awal.",
            "Tambahkan <link rel='preload'> untuk font atau main CSS.",
            "performance", 3)

    # ── HREFLANG (NEW) ─────────────────────────
    if not crawl.get("hreflang_tags") and crawl.get("lang_attribute") != "id":
        add("SEO Internasional", "info",
            "Hreflang tidak ditemukan",
            "Hreflang memberitahu Google versi bahasa mana yang harus ditampilkan kepada user.",
            "Jika website multibahasa, tambahkan rel='alternate' hreflang tags.",
            "technical", 2)

    # ── SECURITY HEADERS (UPDATED) ──────────────
    sec_headers = crawl.get("security_headers") or {}
    if not sec_headers.get("Content-Security-Policy"):
        add("Keamanan", "warning",
            "Content-Security-Policy (CSP) tidak ditemukan",
            "CSP melindungi website dari serangan XSS dan data injection.",
            "Tambahkan header Content-Security-Policy di konfigurasi server.",
            "technical", 5)
    
    if not sec_headers.get("Strict-Transport-Security"):
        add("Keamanan", "info",
            "HSTS header tidak aktif",
            "HSTS memaksa browser menggunakan HTTPS saja secara otomatis.",
            "Aktifkan header Strict-Transport-Security (HSTS).",
            "technical", 3)
    
    if not sec_headers.get("X-Frame-Options"):
        add("Keamanan", "info",
            "X-Frame-Options tidak ditemukan",
            "Header ini mencegah serangan Clickjacking dengan melarang halaman dimuat dalam iframe.",
            "Tambahkan header X-Frame-Options: SAMEORIGIN.",
            "technical", 2)

    # ── TECHNICAL DEBT (NEW) ───────────────────
    deprecated = crawl.get("deprecated_tags") or []
    if deprecated:
        add("SEO Teknikal", "warning",
            f"Tag HTML usang ditemukan: {', '.join(deprecated)}",
            "Tag seperti <font> atau <center> sudah tidak didukung di HTML5 dan menghambat SEO.",
            "Ganti tag usang dengan CSS modern.",
            "technical", 5)
    
    nested_tables = int(crawl.get("nested_tables") or 0)
    if nested_tables > 0:
        add("SEO Teknikal", "info",
            f"Ditemukan {nested_tables} nested tables",
            "Tabel di dalam tabel membuat struktur HTML berat dan sulit dibaca mesin pencari.",
            "Gunakan Flexbox atau CSS Grid untuk tata letak, bukan tabel.",
            "technical", 2)
    
    internal_css = int(crawl.get("internal_css_count") or 0)
    if internal_css > 3:
        add("Performa", "info",
            f"Terlalu banyak internal CSS ({internal_css} blok <style>)",
            "CSS di dalam HTML (internal) tidak bisa di-cache oleh browser secara terpisah.",
            "Pindahkan CSS ke file eksternal (.css).",
            "performance", 3)

    # ── SEMANTIC CONTENT (NEW) ─────────────────
    sems = crawl.get("semantic_tags") or {}
    if sems.get("main", 0) == 0:
        add("Struktur Konten", "info",
            "Tag <main> tidak digunakan",
            "Tag <main> membantu Google dan screen reader fokus pada konten utama.",
            "Gunakan tag <main> untuk membungkus konten utama halaman.",
            "content", 2)
    if sems.get("nav", 0) == 0:
        add("Struktur Konten", "info",
            "Tag <nav> tidak ditemukan",
            "Tag <nav> mendefinisikan navigasi utama situs.",
            "Gunakan tag <nav> untuk menu navigasi.",
            "content", 2)

    # ── E-E-A-T SIGNALS (NEW) ──────────────────
    trust = crawl.get("trust_pages") or {}
    if not trust.get("privacy"):
        add("Kepercayaan (E-E-A-T)", "warning",
            "Halaman Kebijakan Privasi (Privacy Policy) tidak terdeteksi",
            "Google memprioritaskan website yang transparan tentang pengolahan data.",
            "Buat dan tampilkan link Privacy Policy di footer.",
            "social", 8)
    if not trust.get("terms"):
        add("Kepercayaan (E-E-A-T)", "info",
            "Halaman Syarat & Ketentuan (Terms) tidak ditemukan",
            "Terms of Service menunjukkan bisnis yang profesional dan sah.",
            "Tambahkan link Syarat & Ketentuan.",
            "social", 4)

    # ── IMAGE OPTIMIZATION (NEW) ────────────────
    total_imgs = int(crawl.get("total_images") or 0)
    next_gen   = int(crawl.get("next_gen_images") or 0)
    if total_imgs > 3 and next_gen == 0:
        add("Performa", "warning",
            "Format gambar modern (WebP/AVIF) tidak digunakan",
            "Format WebP/AVIF jauh lebih ringan daripada JPG/PNG, mempercepat loading.",
            "Convert gambar kamu ke format WebP untuk menghemat bandwidth.",
            "performance", 8)

    # ── PLACEHOLDER CONTENT (NEW) ───────────────
    if crawl.get("lorem_ipsum_found"):
        add("Kualitas Konten", "critical",
            "Teks placeholder 'Lorem Ipsum' terdeteksi",
            "Google menganggap website dengan Lorem Ipsum sebagai 'Under Construction' atau tidak profesional.",
            "Ganti semua teks simulasi dengan konten asli yang bermanfaat.",
            "content", 15)

    # ── CORE WEB VITALS ADVANCED (NEW) ─────────
    if pagespeed:
        cls_raw = str(pagespeed.get("cls") or "")
        if cls_raw:
            try:
                cls_val = float("".join(c for c in cls_raw if c.isdigit() or c == "."))
                if cls_val > 0.25:
                    add("Core Web Vitals", "critical",
                        f"Layout Shift (CLS) sangat tinggi: {cls_raw} (Target < 0.1)",
                        "CLS mengukur stabilitas visual. Perubahan layout mendadak mengganggu user.",
                        "Berikan dimensi (width/height) pada gambar dan elemen video.",
                        "performance", 10)
                elif cls_val > 0.1:
                    add("Core Web Vitals", "warning",
                        f"CLS perlu perbaikan: {cls_raw}",
                        "Beberapa elemen menyebabkan pergeseran layout saat loading.",
                        "Pastikan semua elemen dinamis memiliki placeholder ukuran tetap.",
                        "performance", 5)
            except ValueError: pass

        tbt_raw = str(pagespeed.get("tbt") or "")
        if tbt_raw:
            try:
                tbt_ms = float("".join(c for c in tbt_raw if c.isdigit()))
                if tbt_ms > 600:
                    add("Core Web Vitals", "critical",
                        f"Total Blocking Time (TBT) sangat tinggi: {tbt_raw}ms",
                        "TBT tinggi berarti browser macet saat memproses JavaScript, menghambat interaksi.",
                        "Kurangi beban JavaScript dari pihak ketiga dan pecah long-tasks.",
                        "performance", 12)
            except ValueError: pass

        # Lighthouse Overall Scores Integration
        a11y = int(pagespeed.get("accessibility_score") or 100)
        if a11y < 85:
            add("Aksesibilitas", "warning",
                f"Accessibility score rendah: {a11y}/100",
                "Meningkatkan aksesibilitas membantu orang berkebutuhan khusus dan disukai Google.",
                "Periksa kontras warna, label tombol, dan urutan heading.",
                "technical", 5)

        bp = int(pagespeed.get("best_practices_score") or 100)
        if bp < 90:
            add("Best Practices", "info",
                f"Best Practices score: {bp}/100",
                "Audit Lighthouse mendeteksi masalah pada keamanan atau standar web modern.",
                "Periksa tab Diagnostics untuk detail perbaikan standar industri.",
                "technical", 4)

    # ── FINALIZE SCORES ────────────────────────
    for k in score:
        score[k] = max(0.0, round(score[k], 1))

    total_score = round(
        score["seo"]         * 0.30 +
        score["technical"]   * 0.25 +
        score["content"]     * 0.20 +
        score["performance"] * 0.15 +
        score["local"]       * 0.05 +
        score["social"]      * 0.05,
        1
    )

    return {
        "total_score": total_score,
        "scores": score,
        "issues": issues,
        "issue_count": {
            "critical": sum(1 for i in issues if i["severity"] == "critical"),
            "warning":  sum(1 for i in issues if i["severity"] == "warning"),
            "info":     sum(1 for i in issues if i["severity"] == "info"),
        }
    }
