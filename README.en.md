# pulse — server vitals timeline

> Samples its own CPU, memory, disk, load and network once a minute, keeps them in SQLite, and draws the last 24 hours with hand-rolled SVG.

English | [中文](README.md)

## What it is

No psutil — everything is read straight from kernel files: CPU usage from the delta of two `/proc/stat` snapshots, memory from `/proc/meminfo`, disk from `statvfs`, and throughput from two reads of `/proc/net/dev` (loopback excluded). The sampler thread lives in the same process as Flask: it takes one sample at startup, then one a minute, writing into the `samples` table and dropping anything older than 14 days. The frontend pulls `/api/recent?hours=N` every 60 seconds and builds SVG paths in plain JavaScript — no Chart.js, no D3.

## Features

- Every metric comes from `/proc` and `statvfs` — Flask is the only dependency
- One sample a minute, deduplicated by `ts` as the primary key, pruned after 14 days
- Four live value cards plus five charts, refreshed every 60 seconds
- Charts are SVG paths generated in the browser — no charting library loaded
- Percentage charts have a minimum Y range so a mostly-idle box still shows a readable curve
- `/api/recent?hours=N` returns the series together with min/avg/max/p95

## Stack

Python 3.12 · Flask 3.1 · SQLite

## Run

```bash
pip install -r requirements.txt
python app.py   # 默认端口 8830，可用 PULSE_PORT 覆盖
```

## About

Part of the **auto-lab** series — small projects written, deployed and maintained automatically by [Nix](https://github.com/Uxnar-ai) on a self-hosted server.

Placeholders such as `<SERVER_IP>` and `<LOCAL_PATH>` are sanitised values applied at publish time. This repository contains no credentials, internal addresses or personal data.

## License

MIT
