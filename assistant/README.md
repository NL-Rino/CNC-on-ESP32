# Trợ lý AI — agent chạy trên web

Một trợ lý AI có **agent loop** thật: nó suy luận, tự gọi công cụ, đọc kết quả, sửa sai rồi
làm tiếp — chứ không chỉ trả lời một lượt. Chạy được ở localhost hoặc deploy lên host miễn phí.

Cái tạo ra cảm giác "AI tự mở ứng dụng làm việc" không phải là model, mà là **kiến trúc này**:

```
Bạn hỏi
  ↓
Claude suy luận (extended thinking)
  ↓
Claude chọn công cụ ──→ server chạy công cụ thật ──→ kết quả quay về Claude
  ↑                                                          │
  └──────────── lặp lại tối đa MAX_TOOL_ROUNDS vòng ─────────┘
  ↓
Trả lời cuối cùng
```

Mọi bước đều stream về trình duyệt qua SSE, nên bạn **thấy** nó đang nghĩ gì và gọi gì.

## Công cụ agent có

| Công cụ | Việc nó làm |
|---|---|
| `run_python` | Chạy Python thật trong tiến trình con có giới hạn CPU/RAM/thời gian |
| `read_file` / `write_file` / `list_files` | Workspace riêng từng phiên chat; file tạo ra tải về được từ sidebar |
| `http_request` | Gọi API công khai (thời tiết, giá coin, REST API…) |
| `web_search` / `web_fetch` | Tìm và đọc web — chạy trên hạ tầng Anthropic, **không cần API key riêng** |
| `remember` / `recall` | Nhớ thông tin về bạn giữa các lượt |

Bật/tắt từng cái bằng biến môi trường (xem `.env.example`).

## Chạy ở máy mình

```bash
cd assistant
cp .env.example .env          # rồi mở ra điền ANTHROPIC_API_KEY
./run.sh                      # mở http://127.0.0.1:8000
```

Windows (PowerShell):

```powershell
cd assistant
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # mở .env điền ANTHROPIC_API_KEY
uvicorn app.server:app --port 8000
```

Lấy API key tại <https://console.anthropic.com/settings/keys>.

## Deploy lên host miễn phí

### Render (dễ nhất, đã có sẵn `render.yaml`)

1. Push repo này lên GitHub.
2. Vào <https://render.com> → **New** → **Blueprint** → chọn repo.
3. Render đọc `render.yaml` và tự tạo service. Điền 2 biến nó hỏi:
   - `ANTHROPIC_API_KEY`
   - `APP_PASSWORD`
4. Xong. Free tier ngủ sau 15 phút không ai dùng, lần gọi đầu chờ ~30 giây.

### Hugging Face Spaces (không ngủ, cần Docker)

1. Tạo Space mới, chọn **Docker** → **Blank**.
2. Upload nội dung thư mục `assistant/` lên Space.
3. Vào **Settings → Variables and secrets**, thêm secret `ANTHROPIC_API_KEY` và `APP_PASSWORD`.

`Dockerfile` đã nghe `$PORT` và mặc định 7860 nên chạy được cả HF Spaces, Fly.io và Railway.

## Cấu hình

Tất cả nằm trong `.env.example` với chú thích. Vài cái đáng chú ý:

- `MODEL` — mặc định `claude-opus-5`. Muốn tiết kiệm thì đổi `claude-sonnet-5`
  (~2.5× rẻ hơn) hoặc `claude-haiku-4-5`.
- `EFFORT` — `low`…`max`. Càng cao suy luận càng sâu, càng tốn token. Mặc định `high`.
- `MAX_TOOL_ROUNDS` — chặn trần số vòng tool để không có vòng lặp tốn tiền vô hạn.
- `ENABLE_SHELL` — mặc định **tắt**. Đọc phần bảo mật dưới trước khi bật.

Chi phí ước tính hiện ở góc sidebar sau mỗi lượt, tính từ `usage` API trả về.

## Bảo mật — đọc phần này trước khi deploy public

**Đặt `APP_PASSWORD`.** Không đặt thì trang mở tự do, ai tìm thấy URL cũng chat được
bằng API key của bạn, và bạn trả tiền.

**`run_python` không phải sandbox thật.** Nó có giới hạn CPU, RAM, số file mở, kích thước
file ghi, thời gian chạy, và `cwd` bị khoá trong workspace của phiên — nhưng code vẫn:

- ra được internet (tiến trình con không bị chặn network);
- đọc được file hệ thống mà user chạy server đọc được.

Server có xoá `ANTHROPIC_API_KEY` và `APP_PASSWORD` khỏi env của tiến trình con, nên code
sinh ra không lấy được key. Nhưng nếu bạn deploy nơi có secret khác hoặc dữ liệu quan trọng,
hãy chạy trong container riêng (Dockerfile sẵn) và coi mọi thứ trong container là công khai.

`ENABLE_SHELL=true` thì mở rộng hẳn bề mặt tấn công — chỉ bật khi chạy local hoặc trong
container dùng-một-lần.

## Cấu trúc code

```
assistant/
├── app/
│   ├── config.py          # đọc biến môi trường
│   ├── agent.py           # agent loop + dịch stream SDK sang event của app
│   ├── server.py          # FastAPI: SSE, đăng nhập, tải file
│   └── tools/
│       ├── registry.py    # khai báo tool (schema + handler)
│       ├── sandbox.py     # chạy tiến trình con có rlimit
│       └── builtin.py     # các tool cụ thể
├── web/                   # giao diện, không dùng thư viện ngoài
├── Dockerfile
├── render.yaml
└── run.sh
```

Thêm tool mới = thêm một `Tool(...)` vào `build_registry()` trong `app/tools/builtin.py`.
Không phải sửa agent loop.

## Vài chi tiết kỹ thuật

- **Adaptive thinking** (`thinking={"type":"adaptive"}`) — model tự quyết định suy luận sâu
  bao nhiêu. `display="summarized"` để lấy được bản tóm tắt mạch suy luận hiển thị lên UI;
  mặc định của Opus 5 là `omitted` (thinking chạy nhưng text rỗng).
- **Gọi tool song song** — một lượt trả lời có thể chứa nhiều `tool_use`. Chúng được chạy
  đồng thời (`asyncio.gather`) và toàn bộ `tool_result` gom vào **đúng một** user message —
  chia ra nhiều message sẽ dạy model thôi gọi song song.
- **Refusal fallback phía server** — nếu Opus 5 từ chối vì chính sách an toàn, API tự chạy
  lại request trên model dự phòng ngay trong cùng một lần gọi thay vì trả về tay trắng.
  Tắt bằng `REFUSAL_FALLBACK=false`.
- **`pause_turn`** — `web_search` chạy lâu có thể bị ngắt giữa lượt; loop gửi lại để tiếp tục.
- **Prompt caching** — system prompt đánh dấu `cache_control` nên các lượt sau đọc từ cache
  rẻ hơn ~10 lần.

## Đã kiểm thử tới đâu

Chạy được và đã test: bộ tool (15 test), agent loop với stream giả lập (13 test), HTTP
endpoint và hàng rào bảo mật (đăng nhập, path traversal, cách ly phiên).

**Chưa test được:** một cú gọi API Anthropic thật — máy dựng dự án này không có API key.
Đường đi tới API đã xác minh (request build và gửi thành công, chỉ dừng ở bước xác thực
key), nhưng lần đầu bạn chạy với key thật hãy thử một câu đơn giản trước.
