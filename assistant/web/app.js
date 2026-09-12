/* Giao dien chat: doc SSE tu /api/chat roi dung dan tung khoi noi dung. */
const $ = (id) => document.getElementById(id);
const state = {
  token: localStorage.getItem("token") || "",
  session: localStorage.getItem("session") || crypto.randomUUID().replace(/-/g, ""),
  busy: false,
  totalCost: 0,
  totalTokens: 0,
};
localStorage.setItem("session", state.session);

/* ------------------------------------------------------------------ markdown */
const esc = (s) => s.replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* Bo dich markdown toi gian: du cho cau tra loi chat, khong keo them thu vien ngoai. */
function md(src) {
  const blocks = [];
  // Tach code fence ra truoc de khong bi cac luat inline pha hong.
  let text = src.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    blocks.push(`<pre><code data-lang="${esc(lang)}">${esc(code.replace(/\n$/, ""))}</code></pre>`);
    return `@@BLOCK${blocks.length - 1}@@`;
  });

  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>');

  const out = [];
  let list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };

  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();

    const ph = line.match(/^@@BLOCK(\d+)@@$/);
    if (ph) { closeList(); out.push(blocks[+ph[1]]); continue; }
    if (!line.trim()) { closeList(); continue; }

    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) { closeList(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }

    const ul = line.match(/^\s*[-*+]\s+(.*)$/);
    if (ul) {
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      out.push(`<li>${inline(ul[1])}</li>`); continue;
    }

    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (ol) {
      if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
      out.push(`<li>${inline(ol[1])}</li>`); continue;
    }

    const bq = line.match(/^>\s?(.*)$/);
    if (bq) { closeList(); out.push(`<blockquote>${inline(bq[1])}</blockquote>`); continue; }

    closeList();
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  return out.join("");
}

/* ------------------------------------------------------------------ dung UI */
const messages = () => $("messages");

function clearWelcome() {
  const w = messages().querySelector(".welcome");
  if (w) w.remove();
}

function addUser(text) {
  clearWelcome();
  const el = document.createElement("div");
  el.className = "msg msg-user";
  el.innerHTML = `<div class="bubble">${esc(text).replace(/\n/g, "<br>")}</div>`;
  messages().appendChild(el);
  scroll();
}

/* Moi luot tra loi la mot "turn": gom khoi suy luan, cac the tool va van ban. */
function newTurn() {
  const el = document.createElement("div");
  el.className = "msg msg-assistant";
  messages().appendChild(el);

  const turn = { root: el, think: null, thinkBody: null, tools: new Map(), text: null, buffer: "" };

  turn.addThinking = (chunk) => {
    if (!turn.think) {
      const box = document.createElement("div");
      box.className = "think";
      box.innerHTML = `<div class="think-head"><span>🧠</span><span>Đang suy luận…</span></div>
                       <div class="think-body"></div>`;
      box.querySelector(".think-head").onclick = () => box.classList.toggle("collapsed");
      el.appendChild(box);
      turn.think = box;
      turn.thinkBody = box.querySelector(".think-body");
    }
    turn.thinkBody.textContent += chunk;
    turn.thinkBody.scrollTop = turn.thinkBody.scrollHeight;
    scroll();
  };

  turn.finishThinking = () => {
    if (!turn.think) return;
    turn.think.classList.add("collapsed");
    turn.think.querySelector(".think-head span:last-child").textContent = "Mạch suy luận";
  };

  turn.toolStart = (ev) => {
    turn.finishThinking();
    const card = document.createElement("div");
    card.className = "tool collapsed";
    card.innerHTML = `
      <div class="tool-head">
        <span class="tool-dot"></span>
        <span class="tool-name"></span>
        <span class="tool-sub">đang chạy…</span>
      </div>
      <div class="tool-body">
        <div class="lbl">Đầu vào</div><pre class="tool-in">…</pre>
        <div class="lbl">Kết quả</div><pre class="tool-out">…</pre>
      </div>`;
    card.querySelector(".tool-name").textContent = ev.label || ev.name;
    card.querySelector(".tool-head").onclick = () => card.classList.toggle("collapsed");
    el.appendChild(card);
    turn.tools.set(ev.id, card);
    turn.text = null; // van ban sau tool phai nam trong khoi moi
    scroll();
  };

  turn.toolInput = (ev) => {
    const card = turn.tools.get(ev.id);
    if (card) card.querySelector(".tool-in").textContent = ev.input || "(không có)";
  };

  turn.toolEnd = (ev) => {
    const card = turn.tools.get(ev.id);
    if (!card) return;
    card.classList.add(ev.ok ? "done" : "fail");
    card.querySelector(".tool-sub").textContent = ev.ok ? "xong" : "lỗi";
    card.querySelector(".tool-out").textContent = ev.output || "(không có output)";
    if (!ev.ok) card.classList.remove("collapsed");
  };

  turn.addText = (chunk) => {
    turn.finishThinking();
    if (!turn.text) {
      turn.text = document.createElement("div");
      turn.text.className = "bubble cursor";
      el.appendChild(turn.text);
      turn.buffer = "";
    }
    turn.buffer += chunk;
    turn.text.innerHTML = md(turn.buffer);
    scroll();
  };

  turn.error = (msg) => {
    turn.finishThinking();
    const box = document.createElement("div");
    box.className = "err";
    box.textContent = msg;
    el.appendChild(box);
    scroll();
  };

  turn.done = () => {
    turn.finishThinking();
    if (turn.text) turn.text.classList.remove("cursor");
    // Stream co the dut giua chung: dung de the tool quay mai.
    for (const card of turn.tools.values()) {
      if (card.classList.contains("done") || card.classList.contains("fail")) continue;
      card.classList.add("fail");
      card.querySelector(".tool-sub").textContent = "bị ngắt";
    }
  };

  return turn;
}

let pinned = true;
function scroll() {
  if (pinned) messages().scrollTop = messages().scrollHeight;
}

/* ------------------------------------------------------------------ mang */
function headers() {
  const h = { "Content-Type": "application/json" };
  if (state.token) h["Authorization"] = `Bearer ${state.token}`;
  return h;
}

async function send(text) {
  if (state.busy || !text.trim()) return;
  state.busy = true;
  $("send").disabled = true;
  $("status").textContent = "Đang xử lý…";
  $("status").classList.add("busy");

  addUser(text);
  const turn = newTurn();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ message: text, session_id: state.session }),
    });

    if (res.status === 401) { logout(); return; }
    if (!res.ok) throw new Error(`server trả về ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // SSE: cac su kien ngan cach bang mot dong trong.
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const part of parts) {
        const line = part.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        handle(JSON.parse(line.slice(6)), turn);
      }
    }
  } catch (err) {
    turn.error(`Lỗi kết nối: ${err.message}`);
  } finally {
    turn.done();
    state.busy = false;
    $("send").disabled = false;
    $("status").textContent = "Sẵn sàng";
    $("status").classList.remove("busy");
    loadFiles();
  }
}

function handle(ev, turn) {
  switch (ev.type) {
    case "thinking":   turn.addThinking(ev.text); break;
    case "text":       turn.addText(ev.text); break;
    case "tool_start": turn.toolStart(ev); break;
    case "tool_input": turn.toolInput(ev); break;
    case "tool_end":   turn.toolEnd(ev); break;
    case "error":      turn.error(ev.message); break;
    case "done":
      state.totalTokens += (ev.tokens_in || 0) + (ev.tokens_out || 0);
      state.totalCost += ev.cost || 0;
      $("usage").textContent =
        `${state.totalTokens.toLocaleString("vi-VN")} token · ~$${state.totalCost.toFixed(4)}`;
      break;
  }
}

/* ------------------------------------------------------------------ file */
async function loadFiles() {
  try {
    const res = await fetch(`/api/files?session_id=${state.session}`, { headers: headers() });
    if (!res.ok) return;
    const { files } = await res.json();
    const list = $("file-list");
    if (!files.length) {
      list.innerHTML = '<li class="empty">Chưa có file nào</li>';
      return;
    }
    list.innerHTML = files.map((f) => {
      const url = `/api/file?session_id=${state.session}&name=${encodeURIComponent(f.name)}`;
      const kb = (f.size / 1024).toFixed(1);
      return `<li><a href="${url}" download>${esc(f.name)}</a> <span class="file-size">${kb} KB</span></li>`;
    }).join("");
  } catch { /* chua co file thi thoi */ }
}

/* ------------------------------------------------------------------ phien */
function logout() {
  state.token = "";
  localStorage.removeItem("token");
  $("app").classList.add("hidden");
  $("login").classList.remove("hidden");
}

async function boot() {
  const cfg = await (await fetch("/api/config")).json();

  if (cfg.auth_required && !state.token) {
    $("login").classList.remove("hidden");
    return;
  }

  $("login").classList.add("hidden");
  $("app").classList.remove("hidden");
  $("model-name").textContent = cfg.model;
  $("model-meta").textContent = `độ sâu suy luận: ${cfg.effort}`;
  $("tool-list").innerHTML = cfg.tools
    .map((t) => `<li><span>·</span><span>${esc(t.label)}</span></li>`).join("");
  loadFiles();
  $("input").focus();
}

/* ------------------------------------------------------------------ su kien */
$("login-form").onsubmit = async (e) => {
  e.preventDefault();
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: $("password").value }),
  });
  if (!res.ok) { $("login-error").textContent = "Sai mật khẩu."; return; }
  const { token } = await res.json();
  state.token = token;
  localStorage.setItem("token", token);
  boot();
};

const input = $("input");
input.oninput = () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 200) + "px";
};
input.onkeydown = (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    const text = input.value;
    input.value = "";
    input.style.height = "auto";
    send(text);
  }
};
$("send").onclick = () => {
  const text = input.value;
  input.value = "";
  input.style.height = "auto";
  send(text);
};

messages().onscroll = () => {
  const el = messages();
  pinned = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
};

document.addEventListener("click", (e) => {
  if (e.target.classList.contains("sample")) send(e.target.textContent);
});

$("reset").onclick = async () => {
  await fetch("/api/reset", {
    method: "POST", headers: headers(),
    body: JSON.stringify({ session_id: state.session }),
  });
  state.session = crypto.randomUUID().replace(/-/g, "");
  localStorage.setItem("session", state.session);
  location.reload();
};

$("refresh-files").onclick = loadFiles;
$("menu").onclick = () => $("sidebar").classList.toggle("open");

boot();
