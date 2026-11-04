# 🎁 TikTok Rương / Túi Quà — Live Scanner

[![Build & Publish Docker Image](https://github.com/nguyenphuc2010z/tiktok-ruong-tui-scanner/actions/workflows/docker.yml/badge.svg)](https://github.com/nguyenphuc2010z/tiktok-ruong-tui-scanner/actions/workflows/docker.yml)

> **Repo:** https://github.com/nguyenphuc2010z/tiktok-ruong-tui-scanner
> **Docker image:** `ghcr.io/nguyenphuc2010z/tiktok-ruong-tui-scanner:latest`

Website quét **LIVE TikTok có rương (treasure box) và túi quà (goody bag)** theo thời gian thực.
**Không dùng API chính thức, không cần đăng nhập TikTok, không demo — chạy thật 100%.**

---

## ✨ Tính năng

- **Chỉ hiển thị LIVE thật sự có rương / túi** — các live không có quà bị lọc bỏ.
- **Không đăng nhập, không API key** — dùng endpoint công khai (unsigned) của TikTok web.
- **Phát hiện tự động 2 lớp:**
  1. **Polling** phòng live mỗi ~20s (đọc `treasure_box_data`, goody bag trong room info).
  2. **WebSocket thời gian thực** — bắt sự kiện `EnvelopeEvent` (rương/túi vừa xuất hiện) ngay lập tức.
- **Tự động thông báo Admin qua Telegram** — không cần nhập tay, có rương/túi là bắn tin.
- **Bộ lọc linh hoạt:** số xu tối thiểu, ratio (xu/suất) tối thiểu, số người xem, loại (rương/túi), level.
- **Admin panel:** cấu hình Telegram, bộ lọc, danh sách kênh seed, xem log realtime.
- **Giao diện dark TikTok-style** với countdown mở rương, auto-refresh.

---

## 🏗️ Kiến trúc

```
app/
  main.py        FastAPI app + REST API + serve web tĩnh
  db.py          SQLite (WAL): settings, rooms, detections, logs
  tiktok.py      Fetcher unsigned: tìm roomId + lấy room info + parse rương/túi
  scanner.py     Vòng lặp: discover live → poll info → lọc → lưu → notify
  ws_manager.py  Listener WebSocket (thread) bắt sự kiện rương/túi realtime
  notify.py      Gửi Telegram Bot API
web/
  index.html     Trang chủ + danh sách LIVE (tab Rương/Túi, filter, countdown)
  admin.html     Bảng điều khiển admin
  assets/        style.css, app.js, admin.js
seeds.txt        Danh sách username TikTok để dò live
run.sh           Khởi chạy uvicorn
```

### Luồng dữ liệu thật

1. **Discover:** với mỗi seed, gọi
   `https://www.tiktok.com/api-live/user/room/?uniqueId=<user>&sourceType=54`
   → trả `roomId` nếu user đang live.
2. **Room info:** gọi `https://webcast.tiktok.com/webcast/room/info/?room_id=<id>`
   → JSON đầy đủ gồm `treasure_box_data` (rương) và các key goody/lucky bag (túi).
3. **Parse:** `parse_prizes()` tách `{kind: ruong|tui, coins, winners, ratio, level, open_ts}`.
4. **Lưu:** `add_detection()` (chống trùng trong 30 phút).
5. **Notify:** `notify_admin()` bắn Telegram.
6. **Realtime:** `ws_manager` mở WebSocket cho các phòng đông người nhất (free tier
   Euler Stream qua route `fetch_webcast_url`) → bắt `EnvelopeEvent` tức thì.

---

## 🚀 Cài đặt & chạy

```bash
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# hoặc
./run.sh
```

Mở:
- Trang chủ: `http://localhost:8000/`
- Admin:   `http://localhost:8000/admin`  (mật khẩu mặc định: `admin123`)

### Cấu hình nhanh (trong Admin)

| Mục | Ý nghĩa |
|-----|---------|
| Telegram Bot Token | Token bot (tạo qua @BotFather) |
| Telegram Chat ID | ID chat/nhóm nhận thông báo |
| Bật thông báo | Bật/tắt gửi Telegram |
| Xu tối thiểu | Bỏ qua rương/túi có xu thấp hơn |
| Ratio tối thiểu | xu / số suất |
| Poll interval | Chu kỳ quét phòng (giây) |
| Seeds | Danh sách username TikTok cần dò (mỗi dòng 1 user) |
| Max WS | Số phòng tối đa mở WebSocket realtime |

---

## 🔔 Lấy Telegram Chat ID

1. Tạo bot với **@BotFather** → lấy `token`.
2. Nhắn 1 tin cho bot, rồi mở
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → lấy `chat.id`.
3. Nhập token + chat id vào Admin → bấm **Test**.

---

## ⚠️ Lưu ý

- Đây là công cụ **không chính thức**, dùng endpoint công khai của TikTok web.
  TikTok có thể đổi cấu trúc bất kỳ lúc nào; khi đó cần cập nhật parser.
- Danh sách LIVE **trống là bình thường** khi chưa có phòng nào đang mở rương/túi —
  đây là dữ liệu thật, không phải lỗi.
- Không có dữ liệu demo/mô phỏng nào được tạo ra.
- Vui lòng tuân thủ điều khoản sử dụng của TikTok khi vận hành.

---

## 🐳 Chạy lâu dài (production)

### Cách 1 — Docker (khuyến nghị)

```bash
# Build & chạy nền, tự restart khi crash / reboot
docker compose up -d --build

# Xem log
docker compose logs -f

# Cập nhật khi có code mới
git pull && docker compose up -d --build
```

Dữ liệu SQLite được lưu trong volume `scanner-data` nên **không mất khi rebuild**.
Image cũng được tự động build & publish lên **GitHub Container Registry (GHCR)** qua GitHub Actions.

Chạy trực tiếp image đã publish:

```bash
docker run -d --name scanner -p 8000:8000 \
  -v scanner-data:/data \
  --restart unless-stopped \
  ghcr.io/<your-user>/<your-repo>:latest
```

### Cách 2 — systemd trên VPS (Ubuntu/Debian)

```bash
sudo useradd -r -s /bin/false scanner
sudo mkdir -p /opt/tiktok-scanner && sudo chown scanner:scanner /opt/tiktok-scanner
sudo -u scanner git clone <repo-url> /opt/tiktok-scanner
cd /opt/tiktok-scanner
sudo -u scanner python3 -m venv .venv
sudo -u scanner .venv/bin/pip install -r requirements.txt

sudo cp deploy/tiktok-scanner.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tiktok-scanner
sudo systemctl status tiktok-scanner
```

### Cách 3 — Nền tảng PaaS (Render / Railway / Fly.io)

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Disk:** gắn volume tại `/data` và đặt `DB_PATH=/data/data.db` để giữ dữ liệu.

### Biến môi trường

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `PORT` | `8000` | Cổng HTTP |
| `DB_PATH` | `./data.db` | Đường dẫn file SQLite |
| `TELEGRAM_TOKEN` | — | (tùy chọn) token bot |
| `TELEGRAM_CHAT` | — | (tùy chọn) chat id |

> Mật khẩu admin mặc định `admin123` — **hãy đổi ngay** trong trang `/admin` sau khi deploy.

---

## ☁️ Deploy 1-click lên Render (không cần VPS)

Repo đã có sẵn `render.yaml`. Cách làm:

1. Vào https://dashboard.render.com/blueprints
2. Bấm **New Blueprint Instance** → chọn repo `tiktok-ruong-tui-scanner`
3. Render tự đọc `render.yaml`, tạo web service + ổ đĩa 1GB (`/data`) để **giữ dữ liệu lâu dài**
4. Bấm **Apply** → đợi build ~3 phút → có URL dạng `https://tiktok-ruong-tui-scanner.onrender.com`

> Dùng gói **Starter** (~7$/tháng) để có ổ đĩa persistent + không bị sleep.
> Gói Free chạy được nhưng service sẽ ngủ khi không truy cập và mất dữ liệu khi restart.

## 🖥️ Chạy bằng Docker image có sẵn (nhanh nhất trên VPS)

Image đã được GitHub Actions build & publish tự động:

```bash
docker run -d --name scanner \
  -p 8000:8000 \
  -v scanner-data:/data \
  -e DB_PATH=/data/data.db \
  --restart unless-stopped \
  ghcr.io/nguyenphuc2010z/tiktok-ruong-tui-scanner:latest
```

Mở `http://<IP-VPS>:8000` → vào `/admin` (mật khẩu `admin123`) → đổi mật khẩu + nhập Telegram.

## 🔄 Cập nhật phiên bản mới

```bash
docker pull ghcr.io/nguyenphuc2010z/tiktok-ruong-tui-scanner:latest
docker rm -f scanner && docker run -d --name scanner -p 8000:8000 \
  -v scanner-data:/data -e DB_PATH=/data/data.db --restart unless-stopped \
  ghcr.io/nguyenphuc2010z/tiktok-ruong-tui-scanner:latest
```
