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
    "Accept": "application/json",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://shopee.vn/",
    "X-Requested-With": "XMLHttpRequest",
    "X-Api-Source": "pc",
    "X-Shopee-Language": "vi",
    "af-ac-enc-dat": "null",
}

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
    "TikTok": """Viết caption TikTok affiliate cho sản phẩm Shopee. Yêu cầu:
- Hook mạnh 3 giây đầu
- Ngắn gọn 50-80 từ, có emoji trending
- Kêu gọi "Link trong bio"
- 5-8 hashtag viral (#fyp #shopee #dealngon)
CHỈ trả về caption, không giải thích.""",
    "Facebook": """Viết bài đăng Facebook affiliate. Yêu cầu:
- Tự nhiên như người thật review, 100-150 từ
- Liệt kê 3-4 điểm nổi bật bằng ✅
- Giá + link rõ ràng ở cuối
CHỈ trả về nội dung bài đăng, không giải thích.""",
    "Instagram": """Viết caption Instagram affiliate. Yêu cầu:
- Aesthetic, lifestyle feel, 60-80 từ
- Emoji đẹp, link in bio CTA
- 10-15 hashtag mix trending + niche
CHỈ trả về caption, không giải thích.""",
    "Zalo": """Viết tin nhắn Zalo affiliate. Yêu cầu:
- Thân thiện như nhắn bạn bè, 40-60 từ
- Tự nhiên, không quá sales, có link
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
        resp = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
        return resp.url
    except:
        return url

def get_affiliate_link(item_id, shop_id):
    try:
        headers = {**HEADERS, "Content-Type": "application/json"}
        payload = {
            "item_id": int(item_id),
            "shop_id": int(shop_id),
            "source_url": f"https://shopee.vn/product/{shop_id}/{item_id}"
        }
        resp = requests.post(
            "https://affiliate.shopee.vn/api/v2/link/generate",
            headers=headers, cookies=get_cookies(), json=payload, timeout=10
        )
        data = resp.json()
        return (data.get("data") or {}).get("short_link", "")
    except Exception as e:
        print(f"Affiliate link error: {e}")
        return ""

def scrape_shopee_api(shop_id, item_id):
    """Thử nhiều endpoint API khác nhau"""
    endpoints = [
        f"https://shopee.vn/api/v4/item/get?itemid={item_id}&shopid={shop_id}",
        f"https://shopee.vn/api/v2/item/get?itemid={item_id}&shopid={shop_id}",
        f"https://shopee.vn/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}",
    ]
    for url in endpoints:
        try:
            resp = requests.get(url, headers=HEADERS, cookies=get_cookies(), timeout=12)
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
        session.headers.update(HEADERS)
        session.cookies.update(SHOPEE_COOKIES)
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
    print(f"Extracted: shop_id={shop_id}, item_id={item_id}")

    product = None
    if shop_id and item_id:
        product = scrape_shopee_api(shop_id, item_id)
    if not product:
        print("API failed, trying HTML scrape...")
        product = scrape_shopee_html(url)
    if not product:
        return jsonify({"error": "Không thể đọc sản phẩm. Thử paste link dạng shopee.vn/product/..."}), 400

    product["url"] = url
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
            headers=HEADERS, cookies=get_cookies(), timeout=10
        )
        sessions_data = sessions_resp.json()
        sessions_list = (sessions_data.get("data") or {}).get("sessions", [])

        if not sessions_list:
            return jsonify({"items": [], "message": "Không có Flash Sale nào đang diễn ra"})

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
            headers=HEADERS, cookies=get_cookies(), timeout=12
        )
        items_data = items_resp.json()
        raw_items = (items_data.get("data") or {}).get("items", [])

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
    try:
        resp = requests.get(
            "https://shopee.vn/api/v4/account/basic",
            headers=HEADERS, cookies=get_cookies(), timeout=8
        )
        data = resp.json()
        user = (data.get("data") or {})
        username = user.get("username") or user.get("email") or ""
        if username:
            return jsonify({"ok": True, "message": f"Cookie hợp lệ · Tài khoản: {username}"})
        # fallback: nếu không lấy được user, check status code
        if resp.status_code == 200 and data.get("error", -1) == 0:
            return jsonify({"ok": True, "message": "Cookie hợp lệ ✓"})
        return jsonify({"ok": False, "message": "Cookie đã hết hạn hoặc không hợp lệ"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"Lỗi kết nối: {str(e)}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
