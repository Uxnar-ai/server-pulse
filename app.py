#!/usr/bin/env python3
"""pulse —— 服务器脉搏：每分钟采一次自身指标，落 SQLite，页面画 24 小时曲线。

不依赖 psutil，全部读 /proc 与 statvfs。采样线程与 Web 同进程，
面板「Python项目」命令模式直接 `python app.py` 即可。
"""
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template, request

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "pulse.db")
PORT = int(os.environ.get("PULSE_PORT", "8830"))
SAMPLE_SECONDS = int(os.environ.get("PULSE_INTERVAL", "60"))
KEEP_DAYS = 14

app = Flask(__name__)
_db_lock = threading.Lock()
_last = {"cpu": None}          # 上一次 /proc/stat 快照，用于差分算 CPU 占用
_last_net = {"rx": None, "tx": None, "ts": None}


# ---------------------------------------------------------------- 采集

def _read_cpu():
    """返回 (busy, total) 累计值。用两次差分得出占用率。"""
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
    vals = [int(x) for x in parts]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    total = sum(vals)
    return total - idle, total


def _cpu_pct():
    busy, total = _read_cpu()
    prev = _last.get("cpu")
    _last["cpu"] = (busy, total)
    if not prev:
        return 0.0
    db, dt = busy - prev[0], total - prev[1]
    if dt <= 0:
        return 0.0
    return round(max(0.0, min(100.0, db * 100.0 / dt)), 1)


def _mem_pct():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.strip().split()[0])
    total = info["MemTotal"]
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    return round((total - avail) * 100.0 / total, 1)


def _disk_pct():
    st = os.statvfs("/")
    used = st.f_blocks - st.f_bfree
    return round(used * 100.0 / st.f_blocks, 1)


def _net_rate():
    """返回 (rx_kbps, tx_kbps)。只统计非回环网卡。"""
    rx = tx = 0
    with open("/proc/net/dev") as f:
        for line in f.readlines()[2:]:
            name, data = line.split(":", 1)
            if name.strip() == "lo":
                continue
            cols = data.split()
            rx += int(cols[0])
            tx += int(cols[8])
    now = time.time()
    prev = _last_net
    rate = (0.0, 0.0)
    if prev["ts"]:
        span = max(0.001, now - prev["ts"])
        rate = ((rx - prev["rx"]) / span / 1024.0,
                (tx - prev["tx"]) / span / 1024.0)
    prev.update(rx=rx, tx=tx, ts=now)
    return round(max(0.0, rate[0]), 1), round(max(0.0, rate[1]), 1)


def _load1():
    try:
        return round(os.getloadavg()[0], 2)
    except OSError:
        return 0.0


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _db_lock, _connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS samples(
            ts    INTEGER PRIMARY KEY,
            cpu   REAL, mem REAL, disk REAL,
            load1 REAL, rx REAL, tx REAL
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ts ON samples(ts)")


def sample_once():
    cpu = _cpu_pct()
    mem = _mem_pct()
    disk = _disk_pct()
    load1 = _load1()
    rx, tx = _net_rate()
    ts = int(time.time())
    with _db_lock, _connect() as c:
        c.execute("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?)",
                  (ts, cpu, mem, disk, load1, rx, tx))
    return {"ts": ts, "cpu": cpu, "mem": mem, "disk": disk,
            "load1": load1, "rx": rx, "tx": tx}


def sampler():
    # 先立刻采一次，保证页面首次打开就有数；之后按间隔循环
    while True:
        try:
            sample_once()
        except Exception as e:                     # 单次失败不杀线程
            print(f"[pulse] 采样失败: {e}", flush=True)
        try:
            if int(time.time()) % 3600 < SAMPLE_SECONDS:
                with _db_lock, _connect() as c:
                    c.execute("DELETE FROM samples WHERE ts < ?",
                              (int(time.time()) - KEEP_DAYS * 86400,))
        except Exception:
            pass
        time.sleep(SAMPLE_SECONDS)


# ---------------------------------------------------------------- 查询

def query_series(hours):
    since = int(time.time()) - hours * 3600
    with _db_lock, _connect() as c:
        rows = c.execute(
            "SELECT ts,cpu,mem,disk,load1,rx,tx FROM samples "
            "WHERE ts >= ? ORDER BY ts", (since,)).fetchall()
    keys = ("ts", "cpu", "mem", "disk", "load1", "rx", "tx")
    return [dict(zip(keys, r)) for r in rows]


def stats(series, field):
    vals = [s[field] for s in series if s[field] is not None]
    if not vals:
        return {"min": 0, "avg": 0, "max": 0, "last": 0}
    order = sorted(vals)
    p95 = order[int(len(order) * 0.95) - 1] if len(order) > 1 else order[0]
    return {"min": round(min(vals), 1), "avg": round(sum(vals) / len(vals), 1),
            "max": round(max(vals), 1), "last": round(vals[-1], 1),
            "p95": round(p95, 1)}


def build_payload(hours):
    series = query_series(hours)
    fields = ("cpu", "mem", "disk", "load1", "rx", "tx")
    return {
        "series": series,
        "count": len(series),
        "hours": hours,
        "interval": SAMPLE_SECONDS,
        "keep_days": KEEP_DAYS,
        "stats": {f: stats(series, f) for f in fields},
        "uptime": uptime_text(),
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def uptime_text():
    try:
        up = int(float(open("/proc/uptime").read().split()[0]))
    except Exception:
        return "—"
    d, rem = divmod(up, 86400)
    h, rem = divmod(rem, 3600)
    return f"{d} 天 {h} 时 {rem // 60} 分"


# ---------------------------------------------------------------- 路由

@app.route("/")
def index():
    hours = max(1, min(168, int(request.args.get("hours", 24))))
    return render_template("index.html", st=build_payload(hours))


@app.route("/api/recent")
def api_recent():
    hours = max(1, min(168, int(request.args.get("hours", 24))))
    return jsonify(build_payload(hours))


@app.route("/healthz")
def healthz():
    return {"ok": True, "samples": len(query_series(1))}


if __name__ == "__main__":
    init_db()
    threading.Thread(target=sampler, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
