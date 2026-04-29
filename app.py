from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import json
import re
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SHOPEE_COOKIES = {
    "SPC_EC": os.getenv("SHOPEE_SPC_EC", ""),
    "SPC_F":  os.getenv("SHOPEE_SPC_F", ""),
}

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
            headers=headers, cookies=SHOPEE_COOKIES, json=payload, timeout=10
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
            resp = requests.get(url, headers=HEADERS, cookies=SHOPEE_COOKIES, timeout=12)
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

    response = client.chat.completions.create(
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
