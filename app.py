from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time
from dotenv import load_dotenv
from openai import OpenAI

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

[HOOK] — 1 câu đầu gây sốc hoặc gây tò mò cực mạnh (KHÔNG hỏi, phải khẳng định)
[PROOF] — 1-2 câu nêu lợi ích thực tế / con số cụ thể
[CTA] — "Link trong bio 👇" hoặc "Bình luận LINK mình gửi ngay"
[HASHTAG] — 5-7 hashtag: mix #fyp #shopee + hashtag niche sản phẩm

Yêu cầu: tổng 50-70 từ, giọng gen Z, emoji đúng chỗ, không sáo rỗng
CHỈ trả về caption, không giải thích.""",
    "Facebook": """Viết bài đăng Facebook affiliate theo cấu trúc sau, tự nhiên như người thật đang chia sẻ:

[HOOK] — 1 câu mở đầu gây tò mò hoặc đồng cảm (có emoji)
[STORY] — 2-3 câu ngắn kể tại sao mua / trải nghiệm thực tế
[ĐIỂM NỔI BẬT] — 3-4 dòng, mỗi dòng bắt đầu bằng ✅, nêu lợi ích cụ thể
[GIÁ & CTA] — Nhấn mạnh giá (nếu có), kêu gọi hành động mạnh
[LINK] — Dòng cuối: "🛒 Xem & đặt hàng tại đây: [link affiliate]"

Yêu cầu thêm:
- Tổng 120-160 từ, giọng văn gần gũi, không cứng nhắc
- Dùng emoji hợp lý (không quá 6 emoji)
- KHÔNG viết "Chào cả nhà" — bắt đầu thẳng vào hook
CHỈ trả về nội dung bài đăng, không giải thích.""",
    "Instagram": """Viết caption Instagram affiliate theo cấu trúc:

[HOOK] — 1 câu mở đầu aesthetic, lifestyle feel (có emoji)
[VIBE] — 2-3 câu tả cảm giác / trải nghiệm dùng sản phẩm, viết như đang sống trong khoảnh khắc đó
[CTA] — "Link in bio 🔗" + gợi ý hành động (save, share, tag bạn)
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
            image_url = f"https://down-vn.img.susercontent.com/file/{images[0]}" if images else ""

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

def scrape_shopee_html(url):
    """Fallback: scrape từ HTML và schema.org"""
    try:
        clean_url = url.split("?")[0]
        session = requests.Session()
        session.headers.update(get_headers())
        session.cookies.update(get_cookies())
        resp = session.get(clean_url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Tìm trong window.__INITIAL_STATE__ hoặc script data
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
                            images = item.get("images", [])
                            return {
                                "name": item.get("name", ""),
                                "price": f"{price:,}đ".replace(",", ".") if price else "",
                                "image": f"https://down-vn.img.susercontent.com/file/{images[0]}" if images else "",
                                "rating": f"⭐ {item.get('item_rating', {}).get('rating_star', 0):.1f}",
                                "sold": f"{item.get('historical_sold', 0)} đã mua",
                                "commission": "Xem dashboard affiliate",
                                "description": item.get("description", "")[:600],
                                "affiliate_link": "",
                            }
                except:
                    pass

        # Fallback: JSON-LD schema.org
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if data.get("@type") == "Product":
                    offers = data.get("offers", {})
                    price_raw = offers.get("price", "")
                    price_str = f"{int(float(price_raw)):,}đ".replace(",", ".") if price_raw else ""
                    imgs = data.get("image", [])
                    img = imgs[0] if isinstance(imgs, list) and imgs else (imgs if isinstance(imgs, str) else "")
                    return {
                        "name": data.get("name", ""),
                        "price": price_str,
                        "image": img,
                        "rating": f"⭐ {data.get('aggregateRating', {}).get('ratingValue', '')}",
                        "sold": "",
                        "commission": "Xem dashboard affiliate",
                        "description": data.get("description", "")[:600],
                        "affiliate_link": "",
                    }
            except:
                continue

        # Fallback cuối: lấy tên từ title tag
        title = soup.find("title")
        name = title.get_text(strip=True).replace(" | Shopee Việt Nam", "") if title else ""
        return {
            "name": name,
            "price": "", "image": "", "rating": "", "sold": "",
            "commission": "Xem dashboard affiliate",
            "description": "", "affiliate_link": ""
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

@app.route("/api/flash-sale", methods=["GET"])
def flash_sale():
    brand_filter = request.args.get("brand", "").lower().strip()

    try:
        sessions_resp = requests.get(
            "https://shopee.vn/api/v4/flash_sale/get_all_sessions",
            headers=get_headers(), cookies=get_cookies(), timeout=10
        )
        print(f"[flash-sale] sessions status={sessions_resp.status_code} body={sessions_resp.text[:300]}")
        sessions_data = sessions_resp.json()
        sessions_list = (sessions_data.get("data") or {}).get("sessions", [])

        if not sessions_list:
            # Thử endpoint thay thế
            sessions_resp2 = requests.get(
                "https://shopee.vn/api/v4/flash_sale/get_all_sessions?limit=8",
                headers=get_headers(), cookies=get_cookies(), timeout=10
            )
            print(f"[flash-sale] sessions2 status={sessions_resp2.status_code} body={sessions_resp2.text[:300]}")
            sessions_data = sessions_resp2.json()
            sessions_list = (sessions_data.get("data") or {}).get("sessions", [])

        if not sessions_list:
            raw_body = sessions_resp.text[:500]
            return jsonify({"items": [], "message": f"Shopee không trả về session Flash Sale. Response: {raw_body}"})

        now_ms = int(time.time()) * 1000
        active = None
        for s in sessions_list:
            start = s.get("start_time", 0)
            end = s.get("end_time", 0)
            if start < 9999999999:
                start *= 1000
                end *= 1000
            if start <= now_ms <= end:
                active = s
                break
        if not active:
            active = sessions_list[0]

        promo_id = active.get("promotionid") or active.get("promotion_id")
        end_time = active.get("end_time", 0)

        items_resp = requests.get(
            "https://shopee.vn/api/v4/flash_sale/get_items_by_session_id",
            params={"promotionid": promo_id, "category_id": 0, "order": 0, "offset": 0, "limit": 100},
            headers=get_headers(), cookies=get_cookies(), timeout=12
        )
        print(f"[flash-sale] items status={items_resp.status_code} body={items_resp.text[:300]}")
        items_data = items_resp.json()
        raw_items = (items_data.get("data") or {}).get("items", [])
        print(f"[flash-sale] promo_id={promo_id} raw_items={len(raw_items)}")

        brands_to_check = [brand_filter] if brand_filter else BIG_BRANDS
        results = []

        for item in raw_items:
            name = item.get("name") or ""
            if not any(b in name.lower() for b in brands_to_check):
                continue

            price_raw = int(item.get("price", 0) or 0)
            price_before_raw = int(item.get("price_before_discount", 0) or 0)
            price_vnd = price_raw // 100000
            price_before_vnd = price_before_raw // 100000

            discount_pct = 0
            if price_before_vnd > price_vnd > 0:
                discount_pct = round((price_before_vnd - price_vnd) / price_before_vnd * 100)

            images = item.get("images") or []
            if not images:
                img = item.get("image")
                images = [img] if img else []
            image_url = f"https://down-vn.img.susercontent.com/file/{images[0]}" if images else ""

            total_stock = item.get("flash_sale_stock", 0) or 0
            sold_count = item.get("flash_sale_sold_count", 0) or 0
            stock_left = max(0, total_stock - sold_count)
            sold_pct = round(sold_count / total_stock * 100) if total_stock > 0 else 0

            shop_id = str(item.get("shopid", "") or item.get("shop_id", ""))
            item_id = str(item.get("itemid", "") or item.get("item_id", ""))

            results.append({
                "name": name,
                "price": f"{price_vnd:,}đ".replace(",", ".") if price_vnd else "",
                "price_before": f"{price_before_vnd:,}đ".replace(",", ".") if price_before_vnd > price_vnd else "",
                "discount": f"-{discount_pct}%" if discount_pct >= 5 else "",
                "image": image_url,
                "shop_id": shop_id,
                "item_id": item_id,
                "url": f"https://shopee.vn/product/{shop_id}/{item_id}" if shop_id and item_id else "",
                "stock_left": stock_left,
                "sold_pct": sold_pct,
            })

        return jsonify({"items": results[:24], "total": len(results), "session_end": end_time})

    except Exception as e:
        print(f"Flash sale error: {e}")
        return jsonify({"error": f"Lỗi quét Flash Sale: {str(e)}", "items": []})

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
