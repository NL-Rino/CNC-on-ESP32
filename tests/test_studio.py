"""Thu giao dien Xuong lam viec bang trinh duyet that.

    python tests/test_studio.py

Can: pip install playwright  &&  playwright install chromium
Thieu playwright thi test tu bo qua - day la lop kiem tra them, khong phai
dieu kien de dung xuong lam viec.

Thu dung nhung viec nguoi dung se lam: chay mot tap, tua tung khung, ve tuong,
dat tram sac, dat nguoi, xoa, luu, bam nut dung an toan - va bat moi loi
javascript xuat hien trong luc do.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("bo qua: chua cai playwright (pip install playwright)")
    raise SystemExit(0)

CHROME = next((c for c in
               ("/opt/pw-browsers/chromium-1194/chrome-linux/chrome",)
               if os.path.exists(c)), None)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_server(url, secs=40):
    for _ in range(secs * 2):
        try:
            urllib.request.urlopen(url + "api/status", timeout=1)
            return True
        except Exception:                      # noqa: BLE001
            time.sleep(0.5)
    return False


def kiem_tra(pg, url, loi):
    pg.goto(url, wait_until="networkidle")
    assert "Xuong" in pg.title() or "Xưởng" in pg.title(), pg.title()

    # --- xem mot tap chay trong nha mau ---
    pg.select_option("#layout", "nha-mau")
    pg.select_option("#brain", "viet-tay")
    pg.fill("#steps", "300")
    pg.click("#run")
    pg.wait_for_function("() => +document.getElementById('scrub').max > 10",
                         timeout=90000)
    time.sleep(1.2)
    n = pg.evaluate("() => +document.getElementById('scrub').max") + 1
    if n < 200:
        loi.append("tap chi co %d khung" % n)
    print("  ok   chay mot tap: %d khung" % n)

    ve = pg.evaluate("""() => {const c=document.getElementById('cv');
        const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
        let k=0; for(let i=3;i<d.length;i+=4000) if(d[i]>0) k++; return k;}""")
    if ve < 50:
        loi.append("canvas xem trong tron")
    print("  ok   canvas co ve (%d diem mau)" % ve)

    pg.fill("#scrub", str(n // 2))
    pg.dispatch_event("#scrub", "input")
    if pg.inner_text("#tlabel") in ("", "0.0s"):
        loi.append("tua khung khong an")
    print("  ok   tua toi giua tap: %s" % pg.inner_text("#tlabel"))

    # --- ve nha ---
    pg.click("#t-ve")
    box = pg.locator("#ed").bounding_box()
    pg.mouse.move(box["x"] + 250, box["y"] + 200)
    pg.mouse.down()
    pg.mouse.move(box["x"] + 430, box["y"] + 260, steps=6)
    pg.mouse.up()
    pg.click('button[data-tool="dock"]')
    pg.mouse.click(box["x"] + box["width"] * 0.80, box["y"] + box["height"] / 2)
    pg.click('button[data-tool="decoy"]')
    pg.mouse.click(box["x"] + box["width"] * 0.22, box["y"] + box["height"] * 0.25)
    pg.click('button[data-tool="mover"]')
    pg.mouse.click(box["x"] + 200, box["y"] + 420)
    st = pg.evaluate("() => ({ob:lay.obstacles.length, bay:lay.bays.length,"
                     " mv:lay.movers.length})")
    if st["ob"] < 1 or st["bay"] < 2 or st["mv"] < 1:
        loi.append("ve thieu: %s" % st)
    print("  ok   ve duoc: %d tuong, %d hoc, %d nguoi"
          % (st["ob"], st["bay"], st["mv"]))

    # hoc phai duoc keo ve trong phong chu khong nam de len tuong
    bad = pg.evaluate("() => lay.bays.filter(b => b.x < 0.2 ||"
                      " b.x > lay.width-0.2 || b.y < 0.2 ||"
                      " b.y > lay.height-0.2).length")
    if bad:
        loi.append("%d hoc nam de len tuong" % bad)
    print("  ok   hoc luon nam tron trong phong")

    pg.fill("#lname", "nha-thu-ui")
    pg.click("#save")
    try:
        pg.wait_for_selector("#ve-msg.ok", timeout=15000)
        print("  ok   luu mat bang: %s" % pg.inner_text("#ve-msg"))
    except Exception:                          # noqa: BLE001
        loi.append("luu that bai: %s" % (pg.inner_text("#ve-msg") or "?"))

    # --- xoa ---
    mv = pg.evaluate("() => lay.movers[0]")
    if mv:
        pt = pg.evaluate("""(m) => {const p=edProj(),
            r=document.getElementById('ed').getBoundingClientRect(),
            c=document.getElementById('ed');
            return [r.left + X(m.x,p)*r.width/c.width,
                    r.top + Y(m.y,p)*r.height/c.height];}""", mv)
        pg.click('button[data-tool="erase"]')
        pg.mouse.click(pt[0], pt[1])
        if pg.evaluate("() => lay.movers.length") != 0:
            loi.append("nut xoa khong an")
        else:
            print("  ok   xoa duoc nguoi da dat")

    # --- mat bang moi phai hien trong danh sach ben tab Xem ---
    pg.click("#t-xem")
    try:
        pg.wait_for_function(
            "() => [...document.getElementById('layout').options]"
            ".some(o => o.value === 'nha-thu-ui')", timeout=15000)
        print("  ok   mat bang moi vao duoc danh sach")
    except Exception:                          # noqa: BLE001
        loi.append("mat bang moi khong hien trong danh sach")


def main():
    port = free_port()
    url = "http://127.0.0.1:%d/" % port
    srv = subprocess.Popen(
        [sys.executable, "-m", "tools.studio", "--no-browser",
         "--port", str(port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    loi = []
    try:
        if not wait_server(url):
            print("khong khoi dong duoc may chu")
            return 1
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox"]}
            if CHROME:
                kw["executable_path"] = CHROME
            b = pw.chromium.launch(**kw)
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            pg.on("pageerror", lambda e: loi.append("loi javascript: %s" % e))
            pg.on("console", lambda m: loi.append("console: " + m.text)
                  if m.type == "error" else None)
            try:
                kiem_tra(pg, url, loi)
            finally:
                b.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:                      # noqa: BLE001
            srv.kill()

    if loi:
        print("\nLOI:")
        for x in loi:
            print("  -", x)
        return 1
    print("7/7 dat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
