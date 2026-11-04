# 🌐 ĐƯA WEBSITE LÊN MẠNG — Hướng dẫn từng bước (miễn phí)

Mục tiêu: có link dạng `https://tiktok-ruong-tui-scanner.onrender.com` mở được trên điện thoại.

**Không cần thẻ tín dụng. Không cần biết code. Khoảng 5 phút.**

---

## Bước 1 — Tạo tài khoản Render

1. Mở https://render.com
2. Bấm **Get Started** (góc trên phải)
3. Chọn **GitHub** → bấm **Authorize Render** → đăng nhập tài khoản `nguyenphuc2010z`
4. Xong, bạn vào được Dashboard.

> Render là dịch vụ hosting miễn phí, uy tín, dùng chung cho hàng triệu dự án.

---

## Bước 2 — Tạo website từ repo (1 cú bấm)

1. Mở link này: **https://dashboard.render.com/blueprints**
2. Bấm nút **New Blueprint Instance**
3. Trong danh sách repo, chọn **`tiktok-ruong-tui-scanner`**
   *(Nếu không thấy, bấm "Configure account" → cấp quyền cho repo này)*
4. Render sẽ tự đọc file `render.yaml` và hiện ra 1 service tên **tiktok-ruong-tui-scanner**
5. Bấm **Apply** (hoặc **Deploy Blueprint**)

---

## Bước 3 — Đợi build (~3–5 phút)

Render sẽ tự:
- tải code từ GitHub
- build Docker image
- chạy website

Bạn xem tab **Logs**, khi thấy dòng:

```
Application startup complete.
Uvicorn running on http://0.0.0.0:8000
```

là **website đã chạy**. Trạng thái chuyển sang **Live** (màu xanh).

---

## Bước 4 — Lấy link website

Ở đầu trang service, Render hiện URL:

```
https://tiktok-ruong-tui-scanner.onrender.com
```

👉 **Đây chính là website của bạn.** Mở trên điện thoại là thấy giao diện quét LIVE.

Trang quản trị: thêm `/admin`
```
https://tiktok-ruong-tui-scanner.onrender.com/admin
```
Mật khẩu mặc định: `admin123` (đổi ngay sau khi vào).

---

## Bước 5 — Bật thông báo Telegram

Vào **/admin** → mục Telegram:

| Ô | Điền gì |
|---|---|
| Bot Token | Token lấy từ @BotFather |
| Chat ID | ID chat của bạn (xem cách lấy bên dưới) |
| Bật thông báo | Bật ON |

Bấm **Lưu** → bấm **Test** → tin nhắn sẽ về Telegram của bạn.

### Cách lấy Chat ID
1. Mở Telegram, tìm **@BotFather** → gõ `/newbot` → đặt tên → nhận **token**
2. Tìm bot bạn vừa tạo → bấm **Start** → nhắn thử `hello`
3. Mở trên trình duyệt: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Tìm dòng `"chat":{"id":123456789,` → số đó là **Chat ID**

---

## ⚠️ Lưu ý về gói Free của Render

| Đặc điểm | Gói Free |
|---|---|
| Chi phí | **0đ** |
| Website chạy | Có (24/7 nhưng **ngủ sau 15 phút** không ai truy cập) |
| Thức dậy | Tự động, mất ~50 giây khi có người mở |
| Dữ liệu (settings) | **Mất khi restart** → nên đặt Telegram qua biến môi trường |
| Giới hạn | 750 giờ/tháng (đủ dùng 1 website) |

**Cách khắc phục "ngủ":** dùng dịch vụ ping miễn phí như https://uptimerobot.com
→ tạo monitor HTTP trỏ tới `https://<tên>.onrender.com/health`, đặt mỗi 5 phút.
Website sẽ **thức 24/7**.

**Cách giữ cài đặt lâu dài:** vào Render → **Environment** → thêm:

```
TELEGRAM_TOKEN   = 123456:ABC...
TELEGRAM_CHAT    = 123456789
TELEGRAM_ENABLED = 1
ADMIN_PASSWORD   = matkhaucuaban
```

Các biến này **không mất** khi restart.

---

## Nếu muốn chuyên nghiệp hơn (có ổ đĩa giữ dữ liệu)

Nâng gói **Starter** (~7$/tháng) trong Render → **Settings → Instance Type**.
Sau đó sửa `render.yaml`:

```yaml
    plan: starter
    envVars:
      - key: DB_PATH
        value: /data/data.db
    disk:
      name: scanner-data
      mountPath: /data
      sizeGB: 1
```

---

## Phương án khác: VPS (rẻ hơn, ~5$/tháng, chạy thật 24/7 không ngủ)

```bash
# Trên VPS đã cài Docker
docker run -d --name scanner \
  -p 80:8000 \
  -e DB_PATH=/data/data.db \
  -e PORT=8000 \
  -v scanner-data:/data \
  --restart unless-stopped \
  ghcr.io/nguyenphuc2010z/tiktok-ruong-tui-scanner:latest
```

Mở `http://IP-VPS` là xong. Không ngủ, không giới hạn giờ.

---

## Gặp lỗi?

| Lỗi | Cách xử lý |
|---|---|
| Build failed | Vào tab **Logs** của Render, copy dòng lỗi cuối gửi tôi |
| 502 / trang trắng | Đợi thêm 1 phút (đang khởi động) rồi tải lại |
| Không thấy repo trong Blueprint | Bấm **Configure account** → cấp quyền repo `tiktok-ruong-tui-scanner` |
| Danh sách LIVE trống | Bình thường — chưa có phòng nào đang mở rương/túi |
