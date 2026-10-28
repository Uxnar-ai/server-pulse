# pulse · 服务器脉搏

> 每分钟采一次自己的 CPU、内存、磁盘、负载和网络，落 SQLite，用纯手写 SVG 画出 24 小时曲线。

[English](README.en.md) | 中文

## 这是什么

不装 psutil，全部读内核文件：`/proc/stat` 两次快照差分算 CPU 占用，`/proc/meminfo` 算内存，`statvfs` 算磁盘，`/proc/net/dev` 两次读数差分算网速（跳过回环）。采样线程和 Flask 同进程，启动即采一次，之后每分钟一次，写进 SQLite 的 `samples` 表，14 天前的自动删掉。前端每 60 秒拉一次 `/api/recent?hours=N`，用 JS 现场拼 SVG path 画图，不引 Chart.js 也不引 D3。

## 功能

- 指标全部来自 `/proc` 与 `statvfs`，除 Flask 外零依赖
- 每分钟采样一次，`ts` 作主键天然去重，14 天前自动清理
- 首页四个当前值卡片 + 五张曲线图，60 秒自动刷新
- 曲线由 JS 现场生成 SVG path，不加载任何图表库
- 百分比图纵轴有下限，长期低占用时曲线不会贴在底部
- `/api/recent?hours=N` 直接返回序列与 min/avg/max/p95

## 技术栈

Python 3.12 · Flask 3.1 · SQLite

## 运行

```bash
pip install -r requirements.txt
python app.py   # 默认端口 8830，可用 PULSE_PORT 覆盖
```

## 关于

本项目属于「auto-lab」每日自主实验系列——由 [Nix](https://github.com/Uxnar-ai) 在自建服务器上自动生成、部署并维护。

代码中的 `<SERVER_IP>`、`<LOCAL_PATH>` 等占位符是发布时的脱敏处理，实际运行请替换为你自己的值。仓库内不含任何真实凭据、内网地址或私人信息。

## 许可

MIT
