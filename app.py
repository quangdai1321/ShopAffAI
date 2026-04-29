from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time
import threading
import datetime
from dotenv import load_dotenv
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

app = Flask(__name__)
_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY chưa được cấu hình trong Environment Variables")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.json")

def get_cookies():
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, "r") as f:
                data = json.load(f)
            if data.get("SPC_EC") or data.get("SPC_F"):
                return data
        except:
            pass
    return {
        "SPC_EC": os.getenv("SHOPEE_SPC_EC", ""),
        "SPC_F":  os.getenv("SHOPEE_SPC_F", ""),
    }

def save_cookies(spc_ec, spc_f):
    with open(COOKIES_FILE, "w") as f:
        json.dump({"SPC_EC": spc_ec, "SPC_F": spc_f}, f)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://shopee.vn/",
    "Origin": "https://shopee.vn",
    "X-Requested-With": "XMLHttpRequest",
    "X-Api-Source": "pc",
    "X-Shopee-Language": "vi",
    "af-ac-enc-dat": "null",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

def get_headers(with_cookies=True):
    h = dict(HEADERS)
    if with_cookies:
        cookies = get_cookies()
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
        if cookie_str:
            h["Cookie"] = cookie_str
    return h

BIG_BRANDS = [
    "vinamilk", "th true", "milo", "nestl",
    "omo", "comfort", "dove", "sunsilk", "lifebuoy", "clear shampoo",
    "downy", "ariel", "gillette", "pantene", "head & shoulders",
    "johnson", "huggies", "pampers", "bobby",
    "colgate", "oral-b", "sensodyne",
    "ensure", "enfamil", "nan optipro", "similac", "pediasure", "growplus",
    "cerave", "la roche", "bioderma", "eucerin",
    "pond's", "olay", "nivea", "vaseline", "hazeline",
]

HOT_HOURS = {
    "TikTok":    ["11:00", "19:00", "20:00", "21:00"],
    "Facebook":  ["09:00", "12:00", "19:00", "20:00"],
    "Instagram": ["11:00", "19:00", "21:00", "22:00"],
    "Zalo":      ["07:00", "12:00", "17:00", "20:00"],
}

PLATFORM_PROMPTS = {
    "TikTok": """Viết caption TikTok affiliate cho sản phẩm Shopee theo cấu trúc:

[HOOK] — 1 câu đầu gây tò mò cực mạnh (KHÔNG hỏi, phải khẳng định)
[PROOF] — 1-2 câu lợi ích thực tế, ngắn gọn
[CTA] — "Link trong bio 👇" hoặc "Bình luận LINK mình gửi ngay"
[LINK] — Dòng riêng: "🛒 [link affiliate]"
[HASHTAG] — 5-7 hashtag: mix #fyp #shopee + hashtag niche

Yêu cầu: tổng 50-70 từ, giọng gen Z, emoji đúng chỗ, không sáo rỗng
CHỈ trả về caption, không giải thích.""",
    "Facebook": """Viết status Facebook như một người thật vừa mua hàng Shopee, đang nhắn cho bạn bè xem. KHÔNG phải viết quảng cáo.

PHONG CÁCH MẪU (học theo giọng này):
"Ủa sao cái áo này mua mà không hối hận gì luôn 😂
Đặt về định thử thôi, mặc vào là thích liền. Vải mềm hơn mình tưởng, không bí, không nhăn.
✅ Mặc đi làm được luôn
✅ Giặt xong tự thẳng, không cần ủi
✅ Phối quần gì cũng hợp, mình mua 2 màu rồi
Mấy đứa hỏi đặt đây nè 👇 [link]"

LUẬT CỨNG:
- KHÔNG dùng: "cảm thấy rất ưng ý", "rất hợp lý", "mình chọn nó vì", "điểm mình thích nhất là", "chỉ khoảng vài trăm thôi"
- KHÔNG mở đầu bằng "Mình vừa mua"
- KHÔNG viết câu dài giải thích như bài luận
- ✅ phải là use case cụ thể (đi đâu, làm gì) KHÔNG phải tính năng sản phẩm

Độ dài: 80-110 từ, tối đa 3 emoji, kết bằng link ngắn gọn
CHỈ trả về bài đăng.""",
    "Instagram": """Viết caption Instagram affiliate theo cấu trúc:

[HOOK] — 1 câu mở đầu aesthetic, lifestyle feel (có emoji)
[VIBE] — 2-3 câu tả cảm giác / trải nghiệm dùng sản phẩm, tự nhiên như đang sống trong khoảnh khắc đó
[LINK] — Dòng riêng: "🔗 [link affiliate]" (không được bỏ qua dòng này)
[CTA] — "Save lại để không quên nhé!" hoặc "Tag bạn cùng xem 👇"
[HASHTAG] — 10-12 hashtag: mix trending + niche + tiếng Việt

Yêu cầu: 70-90 từ, giọng nhẹ nhàng cuốn hút, không quảng cáo lộ liễu
CHỈ trả về caption, không giải thích.""",
    "Zalo": """Viết tin nhắn Zalo affiliate theo cấu trúc:

[MỞ] — 1 câu tự nhiên như đang nhắn bạn thật (ví dụ: "Ê, tao vừa mua cái này...")
[CHIA SẺ] — 2-3 câu kể thật trải nghiệm, nêu 1-2 điểm thích nhất
[GỢI Ý] — Gợi ý nhẹ nhàng không ép mua, kèm link
[EMOJI] — Dùng 2-3 emoji phù hợp, không quá nhiều

Yêu cầu: 45-60 từ, giọng bạn bè thân thiết, tuyệt đối không có mùi sales
CHỈ trả về tin nhắn, không giải thích.""",
}

def extract_shopee_ids(url):
    clean_url = url.split("?")[0]
    patterns = [
        r'\.vn/.+-i\.(\d+)\.(\d+)',
        r'\.vn/product/(\d+)/(\d+)',
        r'-i\.(\d+)\.(\d+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, clean_url)
        if m:
            return m.group(1), m.group(2)
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1), m.group(2)
    return None, None

def resolve_short_url(url):
    try:
        resp = requests.get(url, headers=get_headers(with_cookies=False), allow_redirects=True, timeout=10)
        return resp.url
    except:
        return url

def get_affiliate_link(item_id, shop_id):
    source_url = f"https://shopee.vn/product/{shop_id}/{item_id}"
    endpoints = [
        ("POST", "https://affiliate.shopee.vn/api/v2/link/generate",
         {"item_id": int(item_id), "shop_id": int(shop_id), "source_url": source_url}),
        ("POST", "https://affiliate.shopee.vn/api/v1/link/generate",
         {"item_id": int(item_id), "shop_id": int(shop_id), "url": source_url}),
    ]
    h = {**get_headers(), "Content-Type": "application/json",
         "Referer": "https://affiliate.shopee.vn/"}
    for method, url, payload in endpoints:
        try:
            resp = requests.post(url, headers=h, cookies=get_cookies(), json=payload, timeout=10)
            print(f"Affiliate [{url}] status={resp.status_code} body={resp.text[:200]}")
            data = resp.json()
            link = (data.get("data") or {}).get("short_link", "") or \
                   (data.get("data") or {}).get("link", "")
            if link:
                return link
        except Exception as e:
            print(f"Affiliate link error [{url}]: {e}")
    return ""

def scrape_shopee_api(shop_id, item_id):
    """Thử nhiều endpoint API khác nhau"""
    endpoints = [
        f"https://shopee.vn/api/v4/item/get?itemid={item_id}&shopid={shop_id}",
        f"https://shopee.vn/api/v2/item/get?itemid={item_id}&shopid={shop_id}",
        f"https://shopee.vn/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}",
        f"https://shopee.vn/api/v4/item/get?itemid={item_id}&shopid={shop_id}&need_deleted_subitems=1",
    ]
    for url in endpoints:
        try:
            resp = requests.get(url, headers=get_headers(), cookies=get_cookies(), timeout=12)
            raw = resp.json()
            # v4 format
            item = raw.get("data") or raw.get("item") or {}
            if not item or not item.get("name"):
                continue

            images = item.get("images", [])
            all_images = [f"https://down-vn.img.susercontent.com/file/{img}" for img in images[:12]]
            image_url = all_images[0] if all_images else ""

            price_raw = item.get("price", 0) or item.get("price_min", 0) or 0
            price = int(price_raw) // 100000
            price_str = f"{price:,}đ".replace(",", ".") if price > 0 else ""

            rating = (item.get("item_rating") or {}).get("rating_star", 0)
            sold = item.get("historical_sold", 0) or item.get("sold", 0) or 0
            sold_str = f"{int(sold)/1000:.0f}k+" if int(sold) >= 1000 else str(sold)

            commission = (
                item.get("coin_earn_label", "") or
                item.get("commission_rate_label", "") or
                "Xem dashboard"
            )

            affiliate_link = get_affiliate_link(item_id, shop_id)

            return {
                "name": item.get("name", ""),
                "price": price_str,
                "image": image_url,
                "images": all_images,
                "rating": f"⭐ {float(rating):.1f}" if rating else "",
                "sold": f"{sold_str} đã mua" if sold else "",
                "commission": commission,
                "description": item.get("description", "")[:600],
                "shop_id": shop_id,
                "item_id": item_id,
                "affiliate_link": affiliate_link,
            }
        except Exception as e:
            print(f"API {url} error: {e}")
            continue
    return None

def _build_img_list(images):
    out = []
    for img in (images or [])[:12]:
        if img.startswith("http"):
            out.append(img)
        else:
            out.append(f"https://down-vn.img.susercontent.com/file/{img}")
    return out

def scrape_shopee_html(url):
    """Fallback: scrape từ HTML và schema.org"""
    try:
        clean_url = url.split("?")[0]
        session = requests.Session()
        session.headers.update(get_headers())
        session.cookies.update(get_cookies())
        resp = session.get(clean_url, timeout=15)
        html_text = resp.text
        soup = BeautifulSoup(html_text, "html.parser")

        # 1. OG tags — nhanh và đáng tin cậy nhất
        og_image = soup.find("meta", property="og:image")
        og_title = soup.find("meta", property="og:title")
        og_desc  = soup.find("meta", property="og:description")
        og_price_tag = soup.find("meta", property="product:price:amount")
        og_img_url = og_image["content"] if og_image and og_image.get("content") else ""

        # Tìm thêm ảnh từ tất cả og:image (Shopee đôi khi có nhiều)
        all_og_imgs = [t["content"] for t in soup.find_all("meta", property="og:image") if t.get("content")]
        print(f"[html-scrape] og_imgs={len(all_og_imgs)}")

        # 2. window.__INITIAL_STATE__
        for script in soup.find_all("script"):
            text = script.string or ""
            if "window.__INITIAL_STATE__" in text:
                try:
                    json_str = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});', text, re.DOTALL)
                    if json_str:
                        state = json.loads(json_str.group(1))
                        item = (state.get("productDetail") or {}).get("item", {})
                        if item.get("name"):
                            price_raw = item.get("price", 0) or 0
                            price = int(price_raw) // 100000
                            imgs = _build_img_list(item.get("images", []))
                            return {
                                "name": item.get("name", ""),
                                "price": f"{price:,}đ".replace(",", ".") if price else "",
                                "image": imgs[0] if imgs else og_img_url,
                                "images": imgs or all_og_imgs,
                                "rating": f"⭐ {item.get('item_rating', {}).get('rating_star', 0):.1f}",
                                "sold": f"{item.get('historical_sold', 0)} đã mua",
                                "commission": "Xem dashboard affiliate",
                                "description": item.get("description", "")[:600],
                                "affiliate_link": "",
                            }
                except:
                    pass

        # 3. JSON-LD schema.org
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if data.get("@type") == "Product":
                    offers = data.get("offers", {})
                    price_raw = offers.get("price", "")
                    price_str = f"{int(float(price_raw)):,}đ".replace(",", ".") if price_raw else ""
                    raw_imgs = data.get("image", [])
                    if isinstance(raw_imgs, str): raw_imgs = [raw_imgs]
                    imgs = _build_img_list(raw_imgs) or all_og_imgs
                    return {
                        "name": data.get("name", ""),
                        "price": price_str,
                        "image": imgs[0] if imgs else "",
                        "images": imgs,
                        "rating": f"⭐ {data.get('aggregateRating', {}).get('ratingValue', '')}",
                        "sold": "",
                        "commission": "Xem dashboard affiliate",
                        "description": data.get("description", "")[:600],
                        "affiliate_link": "",
                    }
            except:
                continue

        # 4. Tìm ảnh Shopee CDN trong toàn bộ HTML bằng regex (cả 2 format cũ và mới)
        # Format cũ: [a-f0-9]{32}  |  Format mới: vn-SHOPID-RANDOM-HASH
        cdn_imgs = list(dict.fromkeys(re.findall(
            r'https://down-vn\.img\.susercontent\.com/file/[a-zA-Z0-9_-]+', html_text
        )))[:12]

        # 4b. Tìm mảng image IDs trong JSON — chỉ lấy array ĐẦU TIÊN có >= 3 ảnh (tránh ảnh sp liên quan)
        if len(cdn_imgs) < 2:
            IMG_ID_RE = re.compile(r'"((?:[a-f0-9]{32}|[a-z]{2}-\d+-[a-zA-Z0-9]+-[a-zA-Z0-9]+))"')
            search_sources = [html_text] + [s.string for s in soup.find_all("script") if s.string]
            for source in search_sources:
                for match in re.findall(r'"images"\s*:\s*\[([^\]]{5,2000})\]', source):
                    ids = IMG_ID_RE.findall(match)
                    if len(ids) >= 3:
                        cdn_imgs = list(dict.fromkeys(
                            f"https://down-vn.img.susercontent.com/file/{h}" for h in ids
                        ))[:12]
                        break
                if len(cdn_imgs) >= 3:
                    break

        # 4c. __NEXT_DATA__ (Next.js SSR data)
        if len(cdn_imgs) < 2:
            next_data_tag = soup.find("script", id="__NEXT_DATA__")
            if next_data_tag and next_data_tag.string:
                try:
                    ndata = json.loads(next_data_tag.string)
                    # traverse looking for images array
                    def _find_images(obj, depth=0):
                        if depth > 8: return []
                        if isinstance(obj, dict):
                            if "images" in obj and isinstance(obj["images"], list):
                                return obj["images"]
                            for v in obj.values():
                                r = _find_images(v, depth+1)
                                if r: return r
                        elif isinstance(obj, list):
                            for item in obj:
                                r = _find_images(item, depth+1)
                                if r: return r
                        return []
                    next_imgs = _find_images(ndata)
                    if next_imgs:
                        cdn_imgs = _build_img_list(next_imgs)[:12]
                except:
                    pass

        # 5. Fallback cuối: title + OG + regex price/rating
        title = soup.find("title")
        name = title.get_text(strip=True).replace(" | Shopee Việt Nam", "") if title else ""
        if og_title and not name:
            name = og_title.get("content", "").replace(" | Shopee Việt Nam", "")

        # Giá từ OG tag hoặc regex trong JSON
        price_str = og_price_tag["content"] + "đ" if og_price_tag else ""
        if not price_str:
            price_matches = re.findall(r'"price"\s*:\s*(\d{8,14})', html_text)
            for p in price_matches:
                vnd = int(p) // 100000
                if vnd >= 1000:  # ít nhất 1.000đ — loại giá rác
                    price_str = f"{vnd:,}đ".replace(",", ".")
                    break

        # Rating từ regex
        rating_str = ""
        r_match = re.search(r'"rating_star"\s*:\s*([\d.]+)', html_text)
        if r_match:
            try:
                rv = float(r_match.group(1))
                if 1.0 <= rv <= 5.0:
                    rating_str = f"⭐ {rv:.1f}"
            except: pass

        # Sold từ regex
        sold_str = ""
        s_match = re.search(r'"historical_sold"\s*:\s*(\d+)', html_text)
        if s_match:
            sv = int(s_match.group(1))
            if sv > 0:
                sold_str = f"{sv//1000}k+" if sv >= 1000 else f"{sv} đã mua"

        all_imgs = cdn_imgs or all_og_imgs
        print(f"[html-scrape] imgs={len(all_imgs)} price={price_str!r} rating={rating_str!r} sold={sold_str!r}")
        return {
            "name": name,
            "price": price_str,
            "image": all_imgs[0] if all_imgs else og_img_url,
            "images": all_imgs or ([og_img_url] if og_img_url else []),
            "rating": rating_str,
            "sold": sold_str,
            "commission": "Xem dashboard affiliate",
            "description": og_desc["content"] if og_desc else "",
            "affiliate_link": "",
        }
    except Exception as e:
        print(f"HTML scrape error: {e}")
        return None

@app.route("/")
def index():
    return render_template("index.html", hot_hours=HOT_HOURS)

@app.route("/api/scrape", methods=["POST"])
def scrape():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "Vui lòng nhập link sản phẩm"}), 400

    if "s.shopee.vn" in url or "shope.ee" in url:
        url = resolve_short_url(url)

    shop_id, item_id = extract_shopee_ids(url)
    print(f"Extracted: shop_id={shop_id}, item_id={item_id}, url={url[:80]}")

    product = None
    if shop_id and item_id:
        product = scrape_shopee_api(shop_id, item_id)
    if not product:
        print("API failed, trying HTML scrape...")
        product = scrape_shopee_html(url)
    if not product:
        hint = ""
        if not shop_id:
            hint = " (không tìm được shop_id từ link)"
        return jsonify({"error": f"Không thể đọc sản phẩm từ Shopee{hint}. Server cloud bị Shopee hạn chế — hãy cập nhật cookie mới tại ⚙️ Cookie"}), 400

    product["url"] = url
    if shop_id and item_id:
        product.setdefault("shop_id", shop_id)
        product.setdefault("item_id", item_id)
    print(f"Result: {product}")
    return jsonify(product)

@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.json
    product = data.get("product", {})
    platform = data.get("platform", "TikTok")
    affiliate_link = data.get("affiliate_link") or product.get("affiliate_link") or "[link affiliate]"

    system_prompt = PLATFORM_PROMPTS.get(platform, PLATFORM_PROMPTS["TikTok"])
    user_message = f"""Sản phẩm: {product.get('name', '')}
Giá: {product.get('price', '')}
Đánh giá: {product.get('rating', '')} | {product.get('sold', '')}
Hoa hồng: {product.get('commission', '')}
Mô tả: {product.get('description', '')}
Link affiliate: {affiliate_link}"""

    response = get_openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        max_tokens=500,
        temperature=0.8,
    )
    return jsonify({"content": response.choices[0].message.content})

@app.route("/api/hot-hours", methods=["GET"])
def get_hot_hours():
    return jsonify(HOT_HOURS)

BRAND_KEYWORDS = {
    "": ["vinamilk", "omo", "milo", "dove", "pantene", "nivea", "colgate", "huggies", "comfort", "lifebuoy"],
    "vinamilk": ["vinamilk"],
    "omo": ["omo"],
    "milo": ["milo"],
    "dove": ["dove"],
    "pantene": ["pantene"],
    "huggies": ["huggies"],
    "nivea": ["nivea"],
    "colgate": ["colgate"],
}

# ── DEAL CACHE ─────────────────────────────────────────────────────
_deals_cache = {
    "items": [],
    "updated_at": None,   # "HH:MM DD/MM"
    "scanning": False,
    "error": None,
}

def _build_image_url(img_id):
    if not img_id:
        return ""
    if img_id.startswith("http"):
        return img_id
    return f"https://down-vn.img.susercontent.com/file/{img_id}"

def _search_keyword_html(keyword):
    """Scrape trang HTML tìm kiếm Shopee — ít bị geo-block hơn JSON API"""
    try:
        url = f"https://shopee.vn/search?keyword={requests.utils.quote(keyword)}&sortBy=sales&order=desc"
        html_headers = dict(get_headers())
        html_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        html_headers.pop("X-Requested-With", None)
        html_headers.pop("X-Api-Source", None)
        resp = requests.get(url, headers=html_headers, cookies=get_cookies(), timeout=15)
        html = resp.text
        print(f"[deal-html] keyword={keyword!r} status={resp.status_code} html_len={len(html)}")

        # Tìm __NEXT_DATA__ (Next.js SSR)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
        if m:
            ndata = json.loads(m.group(1))
            # Tìm mảng items trong cấu trúc Next.js
            def _dig(obj, depth=0):
                if depth > 10: return []
                if isinstance(obj, dict):
                    for k in ("items", "searchItems", "search_items", "result"):
                        if k in obj and isinstance(obj[k], list) and len(obj[k]) > 2:
                            return obj[k]
                    for v in obj.values():
                        r = _dig(v, depth+1)
                        if r: return r
                elif isinstance(obj, list) and len(obj) > 2:
                    if isinstance(obj[0], dict) and ("itemid" in obj[0] or "item_basic" in obj[0]):
                        return obj
                    for item in obj:
                        r = _dig(item, depth+1)
                        if r: return r
                return []
            items = _dig(ndata)
            if items:
                print(f"[deal-html] Found {len(items)} items via __NEXT_DATA__")
                return items

        # Tìm window.__INITIAL_STATE__
        m2 = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});\s*</script>', html, re.DOTALL)
        if m2:
            state = json.loads(m2.group(1))
            items = _dig(state) if 'ndata' not in dir() else []
            if not items:
                def _dig2(obj, depth=0):
                    if depth > 8: return []
                    if isinstance(obj, dict):
                        for k in ("items", "searchItems", "result"):
                            if k in obj and isinstance(obj[k], list) and len(obj[k]) > 2:
                                return obj[k]
                        for v in obj.values():
                            r = _dig2(v, depth+1)
                            if r: return r
                    return []
                items = _dig2(state)
            if items:
                print(f"[deal-html] Found {len(items)} items via __INITIAL_STATE__")
                return items

        print(f"[deal-html] No items found in HTML for {keyword!r}")
        return []
    except Exception as e:
        print(f"[deal-html] Error for {keyword!r}: {e}")
        return []

def _search_keyword(keyword):
    """Thử JSON API trước, fallback sang HTML scrape"""
    endpoints = [
        ("https://shopee.vn/api/v4/search/search_items", {
            "keyword": keyword, "limit": 30, "newest": 0,
            "order": "desc", "by": "sales", "version": 2,
            "page_type": "search", "scenario": "PAGE_GLOBAL_SEARCH",
        }),
    ]
    for url, params in endpoints:
        try:
            resp = requests.get(url, params=params, headers=get_headers(),
                                cookies=get_cookies(), timeout=12)
            data = resp.json()
            err = data.get("error") or data.get("err") or 0
            if err and int(err) != 0:
                print(f"[deal-scan] API geo-blocked ({err}), trying HTML fallback for {keyword!r}")
                break
            items = (data.get("data") or {}).get("items", [])
            if items:
                print(f"[deal-scan] API ok: {len(items)} items for {keyword!r}")
                return items
        except Exception as e:
            print(f"[deal-scan] API error for {keyword!r}: {e}")

    # Fallback: HTML scrape
    return _search_keyword_html(keyword)

def _process_search_items(items, seen):
    """Chuyển đổi raw API items thành deal objects"""
    results = []
    for item in items:
        info = item.get("item_basic") or item
        item_id = str(info.get("itemid", ""))
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)

        price_raw    = int(info.get("price", 0) or 0)
        price_min    = int(info.get("price_min", 0) or 0)
        price_before = int(info.get("price_before_discount", 0) or 0)
        price_min_before = int(info.get("price_min_before_discount", 0) or 0)
        actual_price  = price_raw or price_min
        actual_before = price_before or price_min_before
        raw_discount  = int(info.get("raw_discount") or info.get("discount") or 0)
        price_vnd        = actual_price // 100000
        price_before_vnd = actual_before // 100000 if actual_before > actual_price else 0

        if price_before_vnd > price_vnd > 0:
            discount_pct = round((price_before_vnd - price_vnd) / price_before_vnd * 100)
        elif raw_discount > 0:
            discount_pct = raw_discount
            price_before_vnd = 0
        else:
            discount_pct = 0

        images    = info.get("images") or []
        image_url = _build_image_url(images[0]) if images else ""
        shop_id   = str(info.get("shopid", ""))
        sold      = int(info.get("sold", 0) or 0)
        sold_str  = f"{sold//1000}k+" if sold >= 1000 else (str(sold) if sold else "")
        rating    = float((info.get("item_rating") or {}).get("rating_star", 0) or 0)
        name      = info.get("name", "")

        if not price_vnd or not name:
            continue

        results.append({
            "name": name,
            "price": f"{price_vnd:,}đ".replace(",", "."),
            "price_before": f"{price_before_vnd:,}đ".replace(",", ".") if price_before_vnd else "",
            "discount": f"-{discount_pct}%" if discount_pct >= 5 else "",
            "discount_num": discount_pct,
            "image": image_url,
            "shop_id": shop_id,
            "item_id": item_id,
            "url": f"https://shopee.vn/product/{shop_id}/{item_id}",
            "sold_pct": min(85, discount_pct) if discount_pct else 30,
            "stock_left": sold_str,
            "rating": f"⭐{rating:.1f}" if rating >= 1 else "",
            # tag brand để filter client-side
            "brand_tag": name.lower(),
        })
    return results

def scan_all_deals():
    """Background job: quét tất cả brands, lưu vào cache"""
    global _deals_cache
    if _deals_cache["scanning"]:
        print("[scheduler] Already scanning, skip")
        return
    _deals_cache["scanning"] = True
    print("[scheduler] Deal scan started")
    try:
        all_results = []
        seen = set()
        any_ok = False
        for keyword in BRAND_KEYWORDS[""]:
            raw_items = _search_keyword(keyword)
            if raw_items:
                any_ok = True
            processed = _process_search_items(raw_items, seen)
            all_results.extend(processed)
            time.sleep(0.5)  # tránh rate limit

        all_results.sort(key=lambda x: x["discount_num"], reverse=True)
        for r in all_results:
            del r["discount_num"]

        now = datetime.datetime.now().strftime("%H:%M %d/%m")
        if any_ok:
            _deals_cache["items"] = all_results[:60]
            _deals_cache["updated_at"] = now
            _deals_cache["error"] = None
            print(f"[scheduler] Cached {len(all_results)} deals at {now}")
        else:
            _deals_cache["error"] = "geo-blocked"
            _deals_cache["updated_at"] = now
            print(f"[scheduler] All APIs blocked at {now}")
    except Exception as e:
        print(f"[scheduler] Error: {e}")
    finally:
        _deals_cache["scanning"] = False

@app.route("/api/flash-sale", methods=["GET"])
def flash_sale():
    brand_filter = request.args.get("brand", "").lower().strip()
    items = _deals_cache.get("items") or []
    updated_at = _deals_cache.get("updated_at")
    scanning = _deals_cache.get("scanning", False)

    # Filter theo brand
    if brand_filter and items:
        kws = BRAND_KEYWORDS.get(brand_filter, [brand_filter])
        items = [it for it in items if any(k in it.get("brand_tag", "") for k in kws)]

    # Xóa brand_tag khỏi response
    clean = [{k: v for k, v in it.items() if k != "brand_tag"} for it in items]

    if not clean:
        if scanning:
            msg = "Đang quét lần đầu, thử lại sau 1 phút..."
        elif _deals_cache.get("error") == "geo-blocked":
            msg = "Server cloud bị Shopee giới hạn IP. Hãy cập nhật cookie mới tại ⚙️ Cookie rồi thử lại."
        elif not updated_at:
            msg = "Chưa có dữ liệu — đang quét lần đầu..."
        else:
            msg = "Không tìm thấy sản phẩm phù hợp."
        return jsonify({"items": [], "message": msg, "updated_at": updated_at, "scanning": scanning})

    return jsonify({
        "items": clean[:24],
        "total": len(clean),
        "updated_at": updated_at,
        "scanning": scanning,
        "session_end": 0,
    })

@app.route("/api/flash-sale/refresh", methods=["POST"])
def refresh_deals():
    if _deals_cache.get("scanning"):
        return jsonify({"ok": False, "message": "Đang quét rồi, chờ xíu..."})
    threading.Thread(target=scan_all_deals, daemon=True).start()
    return jsonify({"ok": True, "message": "Đang quét lại..."})

@app.route("/settings")
def settings_page():
    cookies = get_cookies()
    return render_template("settings.html",
        has_spc_ec=bool(cookies.get("SPC_EC")),
        has_spc_f=bool(cookies.get("SPC_F")),
    )

@app.route("/api/settings/cookies", methods=["POST"])
def update_cookies():
    data = request.json
    spc_ec = (data.get("SPC_EC") or "").strip()
    spc_f  = (data.get("SPC_F")  or "").strip()
    if not spc_ec or not spc_f:
        return jsonify({"error": "Vui lòng nhập đủ SPC_EC và SPC_F"}), 400
    save_cookies(spc_ec, spc_f)
    return jsonify({"ok": True, "message": "Đã lưu cookie thành công!"})

@app.route("/api/settings/test", methods=["GET"])
def test_cookies():
    cookies = get_cookies()
    spc_ec = cookies.get("SPC_EC", "")
    spc_f  = cookies.get("SPC_F", "")

    # Kiểm tra format cơ bản
    if not spc_ec or not spc_f:
        return jsonify({"ok": False, "message": "Chưa có cookie — hãy paste SPC_EC và SPC_F"})
    if len(spc_ec) < 20 or len(spc_f) < 8:
        return jsonify({"ok": False, "message": "Cookie trông không hợp lệ (quá ngắn)"})

    # Test thực tế: cào 1 sản phẩm Shopee Mall phổ biến
    try:
        resp = requests.get(
            "https://shopee.vn/api/v4/item/get?itemid=1389944&shopid=431876",
            headers=HEADERS, cookies=cookies, timeout=10
        )
        data = resp.json()
        item = (data.get("data") or data.get("item") or {})
        if item.get("name"):
            return jsonify({"ok": True, "message": f"Cookie hoạt động tốt ✓ (test với: {item['name'][:40]}...)"})
        # Shopee trả về 200 nhưng không có item — vẫn ok nếu không bị block
        if resp.status_code == 200:
            return jsonify({"ok": True, "message": "Cookie đã lưu và có định dạng hợp lệ ✓ (thử cào 1 sản phẩm để xác nhận)"})
        return jsonify({"ok": False, "message": f"Shopee trả lỗi {resp.status_code} — cookie có thể đã hết hạn"})
    except Exception as e:
        # Nếu không kết nối được Shopee từ server, vẫn trust cookie nếu format đúng
        return jsonify({"ok": True, "message": "Cookie đã lưu ✓ (không thể ping Shopee từ server — hãy thử cào sản phẩm để xác nhận)"})

# ── SCHEDULER ──────────────────────────────────────────────────────
_scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
_scheduler.add_job(scan_all_deals, "interval", minutes=5, id="deal_scan", max_instances=1)
_scheduler.start()
# Quét lần đầu sau 10 giây (đợi server khởi động xong)
threading.Timer(10.0, scan_all_deals).start()
print("[scheduler] Started — will scan every 5 minutes")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
