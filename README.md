# Shopee Affiliate AI Tool

Web app tự động cào sản phẩm Shopee và tạo nội dung đăng mạng xã hội bằng AI.

## Tính năng
- Cào thông tin sản phẩm từ link Shopee (hỗ trợ link ngắn s.shopee.vn)
- Tạo caption/nội dung cho TikTok, Facebook, Instagram, Zalo
- Lịch đăng bài tối ưu với khung giờ vàng theo từng nền tảng
- Lịch sử nội dung đã tạo

## Cài đặt

### 1. Cài Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Cấu hình API Key
Tạo file `.env` hoặc set biến môi trường:
```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
```

Hoặc trên Windows:
```cmd
set ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
```

### 3. Chạy app
```bash
python app.py
```

### 4. Mở trình duyệt
Vào: http://localhost:5000

## Cách dùng

1. **Dán link sản phẩm Shopee** vào ô đầu tiên
   - Hỗ trợ: `shopee.vn/product/xxx`, `s.shopee.vn/xxx`, `shopee.vn/tên-sp-i.xxx.xxx`
2. **Dán link affiliate** của bạn từ dashboard Shopee Affiliate
3. **Chọn nền tảng** muốn đăng (TikTok / Facebook / Instagram / Zalo)
4. **Nhấn "Tạo nội dung AI"** và chờ vài giây
5. **Chọn khung giờ vàng** để lên lịch đăng
6. **Copy nội dung** và đăng lên mạng xã hội

## Khung giờ vàng
| Nền tảng | Giờ vàng |
|----------|---------|
| TikTok | 11h, 19h, 20h, 21h |
| Facebook | 9h, 12h, 19h, 20h |
| Instagram | 11h, 19h, 21h, 22h |
| Zalo | 7h, 12h, 17h, 20h |

## Nâng cấp tiếp theo
- Tích hợp Shopee Affiliate API để lấy link tự động
- Auto đăng Facebook qua Graph API
- Tạo video prompt cho Google Veo 3
- Lên lịch đăng tự động với scheduler
