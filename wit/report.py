#!/usr/bin/env python3
"""WIT Destek rapor sayfasi.

RustDesk sunucusunun cihaz veritabanini, kayit dosyalarini ve GitHub indirme
sayilarini okuyup /var/lib/wit-report/index.html dosyasini uretir.
systemd zamanlayicisi (wit-report.timer) bunu 15 dakikada bir calistirir.
"""
import datetime as dt
import glob
import html
import json
import os
import re
import sqlite3
import subprocess
import urllib.request
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Istanbul")
except Exception:  # noqa
    TZ = dt.timezone(dt.timedelta(hours=3))

OUT_DIR = "/var/lib/wit-report"
DB = "/var/lib/rustdesk-server/db_v2.sqlite3"
LOG_DIR = "/var/log/rustdesk-server"
REPO = "witdestekwit-lab/wit-destek"
SNAP = os.path.join(OUT_DIR, "downloads.json")
NOW = dt.datetime.now(TZ).replace(tzinfo=None)
DAYS = 30

IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")
TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.\d+)?\s*([+-]\d{2}:?\d{2}|Z)?")


def esc(x):
    return html.escape(str(x if x is not None else ""))


# ---------------------------------------------------------------- cihazlar
def load_devices():
    devs = []
    if not os.path.exists(DB):
        return devs, "veritabani bulunamadi: " + DB
    try:
        con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=5)
        cols = [r[1] for r in con.execute("PRAGMA table_info(peer)")]
        want = [c for c in ("id", "created_at", "info", "note", "status") if c in cols]
        for row in con.execute("SELECT %s FROM peer" % ",".join(want)):
            d = dict(zip(want, row))
            ip = ""
            try:
                ip = json.loads(d.get("info") or "{}").get("ip", "")
            except Exception:
                m = IP_RE.search(str(d.get("info") or ""))
                ip = m.group(1) if m else ""
            ip = str(ip).replace("::ffff:", "")
            created = None
            try:
                created = dt.datetime.fromisoformat(str(d.get("created_at"))[:19]).replace(tzinfo=dt.timezone.utc).astimezone(TZ).replace(tzinfo=None)
            except Exception:
                pass
            devs.append({"id": d.get("id"), "created": created, "ip": ip})
        con.close()
    except Exception as e:  # noqa
        return devs, "veritabani okunamadi: %s" % e
    devs.sort(key=lambda x: x["created"] or dt.datetime.min, reverse=True)
    return devs, ""


# ---------------------------------------------------------------- kayitlar
def read_log(name, max_lines=20000):
    lines = []
    files = sorted(glob.glob(os.path.join(LOG_DIR, name + "*")))
    for f in files:
        try:
            with open(f, errors="replace") as fh:
                lines.extend(fh.read().splitlines()[-max_lines:])
        except Exception:
            pass
    if not lines:
        try:
            out = subprocess.run(
                ["journalctl", "-u", "rustdesk-" + name, "--since", "-%dd" % DAYS,
                 "--no-pager", "-o", "short-iso"],
                capture_output=True, text=True, timeout=30).stdout
            lines = out.splitlines()
        except Exception:
            pass
    return lines[-max_lines:]


def line_time(line):
    m = TS_RE.search(line)
    if not m:
        return None
    try:
        t = dt.datetime.fromisoformat(m.group(1) + " " + m.group(2))
        off = m.group(3)
        if off:
            off = "+00:00" if off == "Z" else (off if ":" in off else off[:3] + ":" + off[3:])
            t = t.replace(tzinfo=dt.timezone(dt.timedelta(hours=int(off[:3]), minutes=int(off[0] + off[4:6]))))
            t = t.astimezone(TZ).replace(tzinfo=None)
        return t
    except Exception:
        return None


RE_NEW = re.compile(r"New relay request (\S+) from \[?(?:::ffff:)?([\d.]+)\]?:(\d+)")
RE_PAIR = re.compile(r"Relayrequest (\S+) from \[?(?:::ffff:)?([\d.]+)\]?:(\d+) got paired")
RE_CLOSE = re.compile(r"Relay of \[?(?:::ffff:)?([\d.]+)\]?:(\d+) closed")


def parse_events(hbbs, hbbr):
    """hbbr kayitlarindan aktarmali oturumlari cikarir.
    Dogrudan (P2P) baglantilar sunucudan gecmedigi icin burada gorunmez."""
    pend, sess, by_ep = {}, {}, {}
    for line in hbbr:
        t = line_time(line)
        if not t:
            continue
        m = RE_NEW.search(line)
        if m:
            pend[m.group(1)] = (t, m.group(2))
            continue
        m = RE_PAIR.search(line)
        if m:
            uuid = m.group(1)
            t0, ip_a = pend.pop(uuid, (t, ""))
            e = {"t": t0, "a": ip_a, "b": m.group(2), "end": None}
            sess[uuid] = e
            by_ep[(m.group(2), m.group(3))] = e
            continue
        m = RE_CLOSE.search(line)
        if m:
            e = by_ep.pop((m.group(1), m.group(2)), None)
            if e and not e["end"]:
                e["end"] = t
    ev = []
    for e in sess.values():
        dur = (e["end"] - e["t"]).total_seconds() if e["end"] else None
        e["dur"] = dur
        e["short"] = dur is not None and dur < 3
        e["active"] = e["end"] is None
        ev.append(e)
    ev.sort(key=lambda e: e["t"], reverse=True)
    return ev


def fmt_dur(s):
    if s is None:
        return "devam ediyor"
    s = int(s)
    if s < 60:
        return "%d sn" % s
    if s < 3600:
        return "%d dk %d sn" % (s // 60, s % 60)
    return "%d sa %d dk" % (s // 3600, (s % 3600) // 60)


# ---------------------------------------------------------------- indirmeler
def downloads():
    cur = {}
    err = ""
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/%s/releases?per_page=100" % REPO,
            headers={"User-Agent": "wit-report", "Accept": "application/vnd.github+json"})
        rel = json.load(urllib.request.urlopen(req, timeout=20))
        for r in rel:
            for a in r.get("assets", []):
                n = a["name"]
                if "windows-x86_64" in n:
                    k = "Windows"
                elif "windows-aarch64" in n:
                    k = "Windows ARM"
                elif "macos-aarch64" in n:
                    k = "Mac (M serisi)"
                elif "macos-x86_64" in n:
                    k = "Mac (Intel)"
                else:
                    continue
                cur[k] = cur.get(k, 0) + int(a.get("download_count", 0))
    except Exception as e:
        err = "GitHub'a ulasilamadi: %s" % e
    snaps = {}
    try:
        snaps = json.load(open(SNAP))
    except Exception:
        pass
    if cur:
        snaps[NOW.strftime("%Y-%m-%d")] = cur
        keep = sorted(snaps)[-120:]
        snaps = {k: snaps[k] for k in keep}
        try:
            json.dump(snaps, open(SNAP, "w"))
        except Exception:
            pass
    week_ago = (NOW - dt.timedelta(days=7)).strftime("%Y-%m-%d")
    base = None
    for d in sorted(snaps):
        if d <= week_ago:
            base = snaps[d]
    if base is None and snaps:
        base = snaps[sorted(snaps)[0]]
    delta = {k: v - (base or {}).get(k, 0) for k, v in cur.items()}
    return cur, delta, err, (sorted(snaps)[0] if snaps else "")


# ---------------------------------------------------------------- servis durumu
def svc(name):
    try:
        return subprocess.run(["systemctl", "is-active", name], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:
        return "?"


# ---------------------------------------------------------------- grafik
def bar_chart(series, labels, colors, names, h=180):
    w = 760
    n = len(labels)
    mx = max([max(s) for s in series] + [1])
    bw = (w - 40) / n
    out = ['<svg viewBox="0 0 %d %d" class="chart" role="img">' % (w, h + 40)]
    for i in range(5):
        y = 10 + (h - 10) * i / 4
        v = round(mx * (4 - i) / 4)
        out.append('<line x1="30" x2="%d" y1="%.1f" y2="%.1f" class="grid"/>' % (w, y, y))
        out.append('<text x="26" y="%.1f" class="ax" text-anchor="end">%d</text>' % (y + 4, v))
    k = len(series)
    for i in range(n):
        for j, s in enumerate(series):
            val = s[i]
            bh = (h - 10) * val / mx
            x = 32 + i * bw + j * (bw - 4) / k
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" rx="2"><title>%s %s: %d</title></rect>'
                       % (x, 10 + (h - 10) - bh, max((bw - 4) / k - 1, 1), bh, colors[j], labels[i], names[j], val))
        if i % 5 == 0 or i == n - 1:
            out.append('<text x="%.1f" y="%d" class="ax" text-anchor="middle">%s</text>' % (32 + i * bw + bw / 2, h + 18, labels[i][5:]))
    lx = 40
    for j, nm in enumerate(names):
        out.append('<rect x="%d" y="%d" width="12" height="12" fill="%s" rx="2"/><text x="%d" y="%d" class="ax">%s</text>'
                   % (lx, h + 26, colors[j], lx + 16, h + 36, esc(nm)))
        lx += 20 + 8 * len(nm)
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- sayfa
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    devs, dberr = load_devices()
    hbbs = read_log("hbbs")
    hbbr = read_log("hbbr")
    ev = parse_events(hbbs, hbbr)
    cur, delta, gherr, first_snap = downloads()

    week = NOW - dt.timedelta(days=7)
    new_week = [d for d in devs if d["created"] and d["created"] >= week]
    ev_week = [e for e in ev if e["t"] >= week and not e["short"]]
    labels = [(NOW - dt.timedelta(days=DAYS - 1 - i)).strftime("%Y-%m-%d") for i in range(DAYS)]
    s_dev = [sum(1 for d in devs if d["created"] and d["created"].strftime("%Y-%m-%d") == l) for l in labels]
    s_ev = [sum(1 for e in ev if not e["short"] and e["t"].strftime("%Y-%m-%d") == l) for l in labels]

    cards = [
        ("Kayıtlı cihaz (toplam)", len(devs), "Programı en az bir kez açan bilgisayarlar"),
        ("Yeni cihaz (7 gün)", len(new_week), "Bu hafta ilk kez açılan"),
        ("Aktarmalı oturum (7 gün)", len(ev_week), "Toplam süre: %s" % fmt_dur(sum(e["dur"] or 0 for e in ev_week))),
        ("İndirme (7 gün)", sum(max(v, 0) for v in delta.values()) if cur else "–",
         "GitHub sayaçları" + (" (ölçüm %s tarihinden beri)" % first_snap if first_snap else "")),
    ]

    p = []
    p.append("""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>WIT Destek – Rapor</title><style>
:root{--bg:#f4f5f7;--card:#fff;--ink:#202124;--mut:#6b6f76;--line:#e3e5e8;--y:#f5c400;--d:#202124}
@media(prefers-color-scheme:dark){:root{--bg:#141517;--card:#1e1f22;--ink:#e8e9eb;--mut:#9a9da3;--line:#2c2e32}}
*{box-sizing:border-box}body{margin:0;font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
header{background:#202124;color:#fff;padding:18px 24px;display:flex;align-items:center;gap:14px;border-bottom:4px solid var(--y)}
header b{font-size:20px}header span{color:#bbb;font-size:13px;margin-left:auto}
main{max-width:1100px;margin:0 auto;padding:20px}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.big{font-size:34px;font-weight:700;margin:4px 0}.mut{color:var(--mut);font-size:13px}
h2{font-size:17px;margin:26px 0 10px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600}.chart{width:100%;height:auto}.grid{stroke:var(--line)}.ax{fill:var(--mut);font-size:11px}
.ok{color:#1a7f37;font-weight:600}.bad{color:#cf222e;font-weight:600}
details pre{white-space:pre-wrap;font-size:12px;max-height:380px;overflow:auto;background:var(--bg);padding:10px;border-radius:8px}
.warn{background:#fff4ce;color:#5c4400;border-radius:8px;padding:8px 12px;margin:8px 0}
</style></head><body>""")
    p.append('<header><b>WIT Destek</b> Uzak destek raporu<span>Güncellendi: %s · 15 dakikada bir yenilenir</span></header><main>'
             % NOW.strftime("%d.%m.%Y %H:%M"))
    for e in (dberr, gherr):
        if e:
            p.append('<div class="warn">%s</div>' % esc(e))
    p.append('<div class="grid4">')
    for t, v, s in cards:
        p.append('<div class="card"><div class="mut">%s</div><div class="big">%s</div><div class="mut">%s</div></div>' % (esc(t), esc(v), esc(s)))
    p.append("</div>")

    st_s, st_r = svc("rustdesk-hbbs"), svc("rustdesk-hbbr")
    cls = lambda x: "ok" if x == "active" else "bad"
    p.append('<h2>Sunucu durumu</h2><div class="card">Kimlik sunucusu (hbbs): <span class="%s">%s</span> &nbsp; · &nbsp; Aktarma sunucusu (hbbr): <span class="%s">%s</span></div>'
             % (cls(st_s), "çalışıyor" if st_s == "active" else esc(st_s), cls(st_r), "çalışıyor" if st_r == "active" else esc(st_r)))

    p.append("<h2>Son %d gün</h2><div class='card'>%s</div>" % (DAYS, bar_chart(
        [s_dev, s_ev], labels, ["#f5c400", "#5b8def"], ["Yeni cihaz", "Aktarmalı oturum"])))

    p.append("<h2>İndirmeler (GitHub)</h2><div class='card'><table><tr><th>Platform</th><th>Toplam</th><th>Son 7 gün</th></tr>")
    for k in ("Windows", "Windows ARM", "Mac (M serisi)", "Mac (Intel)"):
        if k in cur:
            p.append("<tr><td>%s</td><td>%d</td><td>%+d</td></tr>" % (k, cur[k], delta.get(k, 0)))
    p.append("</table><div class='mut'>Toplam, eski sürümlerin indirmelerini de içerir. Kimin indirdiği GitHub'da görünmez.</div></div>")

    p.append("<h2>Son aktarmalı oturumlar</h2><div class='card'><table><tr><th>Başlangıç</th><th>Taraf 1 (IP)</th><th>Taraf 2 (IP)</th><th>Süre</th><th></th></tr>")
    for e in ev[:60]:
        note = "kısa deneme / tarama" if e["short"] else ("açık" if e["active"] else "")
        p.append("<tr%s><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='mut'>%s</td></tr>" % (
            " style='opacity:.55'" if e["short"] else "", e["t"].strftime("%d.%m %H:%M"), esc(e["a"]), esc(e["b"]), fmt_dur(e["dur"]), note))
    if not ev:
        p.append("<tr><td colspan=5 class='mut'>Henüz aktarmalı oturum yok.</td></tr>")
    p.append("</table><div class='mut'>Sadece sunucu üzerinden aktarılan oturumlar görünür. İki bilgisayar doğrudan bağlanabildiğinde (çoğu durumda) görüntü sunucudan geçmez ve burada listelenmez. 3 saniyeden kısa oturumlar genelde internet taramasıdır.</div></div>")

    p.append("<h2>Cihazlar (en yeni %d)</h2><div class='card'><table><tr><th>ID</th><th>İlk görülme</th><th>Son IP</th></tr>" % min(len(devs), 100))
    for d in devs[:100]:
        p.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (esc(d["id"]), d["created"].strftime("%d.%m.%Y %H:%M") if d["created"] else "", esc(d["ip"])))
    p.append("</table></div>")

    p.append("<h2>Ham kayıtlar</h2><div class='card'><details><summary>hbbs (son 150 satır)</summary><pre>%s</pre></details>"
             "<details><summary>hbbr (son 150 satır)</summary><pre>%s</pre></details></div>"
             % (esc("\n".join(hbbs[-150:])), esc("\n".join(hbbr[-150:]))))
    p.append("<p class='mut'>WIT Destek · RustDesk tabanlı · bu sayfa sadece ofis ağından ve VPN'den görünür.</p></main></body></html>")

    tmp = os.path.join(OUT_DIR, ".index.tmp")
    with open(tmp, "w") as f:
        f.write("".join(p))
    os.replace(tmp, os.path.join(OUT_DIR, "index.html"))


if __name__ == "__main__":
    main()
