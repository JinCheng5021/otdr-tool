from __future__ import annotations

from datetime import datetime
import hashlib
import io
import json
import time
import sqlite3
import os
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Iterable, List

from .msor_converter import build_workbook_from_uploads
from .blob_storage import (
    DEFAULT_MAX_DOWNLOAD_BYTES,
    BlobStorageConfigurationError,
    BlobStorageError,
    BlobStorageNotFoundError,
    BlobStorageOperationError,
    BlobStorageSizeError,
    PrivateBlobStorage,
    SUPPORTED_INPUT_EXTENSIONS,
    build_input_file_path,
    build_output_path,
    job_id_from_input_file_path,
    job_id_from_input_path,
)

DB_FILE = "/tmp/export_history.db" if os.environ.get("VERCEL") else "export_history.db"

def init_db():
    # Bỏ qua lỗi nếu hệ thống file hoàn toàn read-only và không có /tmp
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS export_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exporter_name TEXT,
                unit TEXT,
                route_name TEXT,
                export_time TEXT
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Could not initialize database. {e}")

init_db()

app = FastAPI(title='FPT Telecom Trace')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = ['.msor', '.sor', '.trc']
INPUT_EXTENSION_PRIORITY = ('.sor', '.msor', '.trc')
XLSX_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
HTML_PAGE = """<!DOCTYPE html>

<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>FPT Telecom OTDR Trace Pro</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
<script id="tailwind-config">
  tailwind.config = {
    darkMode: "class",
    theme: {
      extend: {
        "colors": {
                "surface-tint": "#3350d5",
                "primary-fixed": "#dee1ff",
                "secondary-fixed-dim": "#c6c6c6",
                "on-primary-fixed": "#001159",
                "surface-container-lowest": "#ffffff",
                "secondary-container": "#e2e2e2",
                "error": "#ba1a1a",
                "secondary-fixed": "#e2e2e2",
                "on-tertiary-container": "#ff8f77",
                "on-secondary-container": "#646464",
                "background": "#fbf8ff",
                "on-surface": "#1a1b23",
                "primary": "#001e81",
                "error-container": "#ffdad6",
                "primary-container": "#002eb8",
                "on-error": "#ffffff",
                "tertiary-fixed-dim": "#ffb4a4",
                "on-primary-container": "#99a9ff",
                "surface-bright": "#fbf8ff",
                "secondary": "#5e5e5e",
                "on-secondary-fixed-variant": "#474747",
                "surface-container": "#eeedf8",
                "surface": "#fbf8ff",
                "inverse-on-surface": "#f1effb",
                "on-tertiary-fixed": "#3d0600",
                "tertiary": "#5b0c00",
                "tertiary-fixed": "#ffdad3",
                "surface-container-low": "#f4f2fe",
                "outline-variant": "#c5c5d7",
                "outline": "#757686",
                "tertiary-container": "#831600",
                "on-error-container": "#93000a",
                "surface-variant": "#e2e1ed",
                "primary-fixed-dim": "#b9c3ff",
                "on-tertiary": "#ffffff",
                "surface-container-highest": "#e2e1ed",
                "on-background": "#1a1b23",
                "on-surface-variant": "#444654",
                "inverse-surface": "#2f3038",
                "on-primary-fixed-variant": "#0e34bd",
                "on-secondary": "#ffffff",
                "inverse-primary": "#b9c3ff",
                "surface-dim": "#dad9e4",
                "on-primary": "#ffffff",
                "on-tertiary-fixed-variant": "#8a1c03",
                "surface-container-high": "#e8e7f2",
                "on-secondary-fixed": "#1b1b1b",
                "industrial-navy": "#001e81",
                "industrial-gray": "#444654",
                "status-pass": "#22c55e",
                "status-warning": "#f59e0b",
                "status-fail": "#ef4444"
        },
        "borderRadius": {
                "DEFAULT": "0.125rem",
                "lg": "0.25rem",
                "xl": "0.5rem",
                "full": "0.75rem"
        },
        "spacing": {
                "margin-mobile": "16px",
                "touch-target": "48px",
                "margin-desktop": "40px",
                "gutter": "24px",
                "unit": "8px"
        },
        "fontFamily": {
                "body-lg": ["Inter", "sans-serif"],
                "mono-data": ["JetBrains Mono", "monospace"],
                "label-md": ["Inter", "sans-serif"],
                "headline-lg": ["Inter", "sans-serif"],
                "body-md": ["Inter", "sans-serif"],
                "headline-xl": ["Inter", "sans-serif"],
                "headline-md": ["Inter", "sans-serif"],
                "label-lg": ["Inter", "sans-serif"]
        },
        "animation": {
          "shimmer": "shimmer 2s infinite linear",
          "pulse-soft": "pulse-soft 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
          "fade-up": "fade-up 0.5s ease-out forwards"
        },
        "keyframes": {
          "shimmer": {
            "0%": { "background-position": "-200% 0" },
            "100%": { "background-position": "200% 0" }
          },
          "pulse-soft": {
            "0%, 100%": { "opacity": "1" },
            "50%": { "opacity": "0.6" }
          },
          "fade-up": {
            "0%": { "opacity": "0", "transform": "translateY(20px)" },
            "100%": { "opacity": "1", "transform": "translateY(0)" }
          }
        }
      }
    }
  }
</script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&amp;family=JetBrains+Mono:wght@600&amp;family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<style>
  body {
    background-color: theme('colors.background');
    color: theme('colors.on-background');
    font-family: theme('fontFamily.body-lg');
  }
  .glass-card {
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(0, 30, 129, 0.1);
  }
  .industrial-border {
    border: 1px solid theme('colors.outline');
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
  }
  .btn-pro {
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }
  .btn-pro:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 30, 129, 0.15);
  }
  .btn-pro:active {
    transform: translateY(0);
    scale: 0.98;
  }
  .shimmer-effect {
    background: linear-gradient(90deg, transparent 25%, rgba(255,255,255,0.4) 50%, transparent 75%);
    background-size: 200% 100%;
    animation: shimmer 2.5s infinite;
  }
  .no-scrollbar::-webkit-scrollbar { display: none; }
  .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
  
  .stagger-1 { animation-delay: 0.1s; }
  .stagger-2 { animation-delay: 0.2s; }
  .stagger-3 { animation-delay: 0.3s; }
  .stagger-4 { animation-delay: 0.4s; }
  .advanced-hidden {
    display: none !important;
  }
</style>
</head>
<body class="antialiased min-h-screen flex flex-col selection:bg-primary-fixed selection:text-on-primary-fixed">
<!-- TopAppBar -->
<header class="bg-surface/80 backdrop-blur-md border-b border-outline-variant z-50 sticky top-0 px-margin-mobile md:px-margin-desktop w-full h-14 flex justify-between items-center">
<div class="flex items-center gap-2">
<div class="w-8 h-8 bg-primary rounded flex items-center justify-center text-on-primary">
<span class="material-symbols-outlined text-[20px]">analytics</span>
</div>
<span class="font-headline-md text-[18px] font-extrabold tracking-tight text-industrial-navy">FPT OTDR PRO</span>
</div>
<div class="flex items-center gap-3">
<div class="flex items-center gap-2 text-status-pass bg-status-pass/10 px-3 py-1 rounded-full border border-status-pass/20 animate-pulse-soft">
<div class="w-2 h-2 rounded-full bg-status-pass"></div>
<span class="text-[10px] font-bold uppercase tracking-widest">System Ready</span>
</div>
<div class="relative">
<button id="notifBtn" class="w-8 h-8 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-variant transition-colors relative">
<span class="material-symbols-outlined text-[20px]">notifications</span>
<span id="notifBadge" class="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold rounded-full w-4 h-4 flex items-center justify-center hidden">0</span>
</button>
<div id="notifDropdown" class="absolute right-0 mt-2 w-80 bg-white/95 backdrop-blur-md border border-outline-variant shadow-2xl rounded-xl z-[100] hidden overflow-hidden flex flex-col max-h-96">
<div class="p-4 border-b border-outline-variant flex justify-between items-center bg-surface-container-low">
<span class="font-bold text-xs text-industrial-navy uppercase tracking-wider">Thông báo xuất tuyến</span>
<button id="markAllReadBtn" class="text-[11px] font-bold text-primary hover:underline transition-all">Đọc tất cả</button>
</div>
<div id="notifList" class="overflow-y-auto divide-y divide-outline-variant/50 max-h-72 no-scrollbar">
<div class="p-4 text-center text-xs text-on-surface-variant">Không có thông báo mới</div>
</div>
</div>
</div>

</div>
</header>
<!-- Main Canvas -->
<main class="flex-1 flex flex-col md:flex-row w-full max-w-[1400px] mx-auto relative">
<!-- NavigationDrawer (Desktop Only) -->
<aside class="hidden md:flex flex-col gap-4 p-6 bg-surface-container-low border-r border-outline-variant w-[280px] sticky top-14 h-[calc(100vh-56px)] shrink-0">
<div class="flex flex-col gap-1">
<button class="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-primary text-white shadow-lg shadow-primary/20 btn-pro font-semibold">
<span class="material-symbols-outlined text-[20px]">upload</span>
<span class="text-sm">Nạp Trace Mới</span>
</button>
<div class="h-px bg-outline-variant my-4"></div>
<nav class="flex flex-col gap-1">
<button onclick="window.open('/graph', '_blank')" class="flex items-center gap-3 px-3 py-2 text-left rounded-lg text-on-surface-variant hover:bg-surface-variant transition-colors font-medium">
<span class="material-symbols-outlined text-[20px] text-primary">show_chart</span>
<span class="text-sm font-bold text-primary">Đồ thị tuyến</span>
</button>
<button class="flex items-center gap-3 px-3 py-2 text-left rounded-lg text-primary bg-primary-fixed/50 font-bold border border-primary/10">
<span class="material-symbols-outlined text-[20px]">tune</span>
<span class="text-sm">Cấu hình thông số</span>
</button>
<button class="flex items-center gap-3 px-3 py-2 text-left rounded-lg text-on-surface-variant hover:bg-surface-variant transition-colors font-medium">
<span class="material-symbols-outlined text-[20px]">history</span>
<span class="text-sm">Lịch sử xuất file</span>
</button>
<button class="flex items-center gap-3 px-3 py-2 text-left rounded-lg text-on-surface-variant hover:bg-surface-variant transition-colors font-medium">
<span class="material-symbols-outlined text-[20px]">settings</span>
<span class="text-sm">Tùy chọn hệ thống</span>
</button>
</nav>
</div>
<div class="mt-auto bg-surface-container-high/50 p-4 rounded-xl border border-outline-variant">
<div class="flex items-center gap-2 mb-3">
<span class="material-symbols-outlined text-[18px] text-industrial-navy">info</span>
<span class="text-[11px] font-bold text-on-surface-variant tracking-wider uppercase">Thống kê phiên</span>
</div>
<ul class="space-y-3">
<li class="flex justify-between items-center">
<span class="text-xs text-on-surface-variant">Trace nạp:</span>
<span class="font-mono-data text-sm font-bold text-primary">00</span>
</li>
<li class="flex justify-between items-center">
<span class="text-xs text-on-surface-variant">Lỗi nhận diện:</span>
<span class="font-mono-data text-sm font-bold text-error">00</span>
</li>
<li class="flex justify-between items-center">
<span class="text-xs text-on-surface-variant">Phiên bản:</span>
<span class="font-mono-data text-xs text-on-surface-variant">v2.1.4</span>
</li>
</ul>
</div>
</aside>
<!-- Center Visualization & Configuration Area -->
<div class="flex-1 flex flex-col min-w-0 p-margin-mobile md:p-8 gap-8 pb-24">
<!-- Hero / Title Area -->
<section class="opacity-0 animate-fade-up">
<h1 class="font-headline-xl text-[28px] md:text-headline-xl text-industrial-navy mb-2 tracking-tight">Cấu hình Xuất Excel Tuyến</h1>
<p class="font-body-md text-on-surface-variant max-w-2xl leading-relaxed">Chuẩn hóa dữ liệu đo OTDR sang báo cáo kiểm tra tuyến chuyên nghiệp. Hỗ trợ đầy đủ định dạng .SOR, .MSOR và .TRC.</p>
</section>
<!-- Industrial Drop Zone -->
<section class="opacity-0 animate-fade-up stagger-1">
<div id="dropzone" class="group relative w-full h-56 md:h-64 rounded-2xl border-2 border-dashed border-primary/30 bg-surface-container-lowest hover:bg-primary/5 hover:border-primary transition-all flex flex-col items-center justify-center cursor-pointer overflow-hidden">
<input type="file" id="fileInput" multiple style="display:none" />
<div class="absolute inset-0 shimmer-effect opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></div>
<div class="bg-white p-5 rounded-2xl shadow-sm border border-outline-variant group-hover:border-primary/50 group-hover:scale-110 transition-all duration-500 z-10">
<span class="material-symbols-outlined text-[40px] text-primary">cloud_upload</span>
</div>
<h3 class="font-headline-md text-[20px] text-industrial-navy mt-4 mb-1 z-10">Kéo thả tệp đo tại đây</h3>
<p class="font-body-sm text-on-surface-variant z-10 mb-6">Hệ thống tự động phân loại định dạng</p>
<div class="flex gap-3 z-10">
<span class="px-3 py-1 rounded bg-white border border-outline-variant font-mono-data text-[11px] font-bold text-industrial-gray">.SOR</span>
<span class="px-3 py-1 rounded bg-white border border-outline-variant font-mono-data text-[11px] font-bold text-industrial-gray">.MSOR</span>
<span class="px-3 py-1 rounded bg-white border border-outline-variant font-mono-data text-[11px] font-bold text-industrial-gray">.TRC</span>
</div>
</div>
<div class="files mt-3 flex flex-col gap-2" id="fileList">
  <div class="file-empty text-center text-sm text-on-surface-variant font-medium">Chưa chọn file nguồn.</div>
</div>
<div class="status mt-2 p-4 rounded-xl text-sm hidden" id="status"></div>
</section>
<!-- Stats Bento Grid -->
<section class="grid grid-cols-1 md:grid-cols-3 gap-4 opacity-0 animate-fade-up stagger-2">
<div class="bg-white border border-outline-variant rounded-xl p-5 flex flex-col relative overflow-hidden group">
<div class="absolute inset-0 shimmer-effect opacity-0 group-hover:opacity-100 transition-opacity"></div>
<span class="text-[10px] font-bold text-on-surface-variant tracking-widest uppercase mb-4">ĐỊNH DẠNG HỖ TRỢ</span>
<div class="flex items-baseline gap-2">
<span class="font-mono-data text-4xl text-industrial-navy tracking-tighter">03</span>
<span class="text-xs text-on-surface-variant font-medium">TIÊU CHUẨN</span>
</div>
</div>
<div class="bg-white border border-outline-variant rounded-xl p-5 flex flex-col relative overflow-hidden group">
<div class="absolute inset-0 shimmer-effect opacity-0 group-hover:opacity-100 transition-opacity"></div>
<span class="text-[10px] font-bold text-on-surface-variant tracking-widest uppercase mb-4">THÔNG SỐ XỬ LÝ</span>
<div class="flex items-baseline gap-2">
<span class="font-mono-data text-4xl text-industrial-navy tracking-tighter">07</span>
<span class="text-xs text-on-surface-variant font-medium">CHỈ SỐ KPI</span>
</div>
</div>
<div class="bg-white border border-outline-variant rounded-xl p-5 flex flex-col relative overflow-hidden group">
<div class="absolute inset-0 shimmer-effect opacity-0 group-hover:opacity-100 transition-opacity"></div>
<span class="text-[10px] font-bold text-on-surface-variant tracking-widest uppercase mb-4">CẤU TRÚC ĐẦU RA</span>
<div class="flex items-baseline gap-2">
<span class="font-mono-data text-4xl text-industrial-navy tracking-tighter">03</span>
<span class="text-xs text-on-surface-variant font-medium">SHEET CHÍNH</span>
</div>
</div>
</section>
<!-- Configuration Settings Panel -->
<section class="glass-card rounded-2xl overflow-hidden flex flex-col opacity-0 animate-fade-up stagger-3 border border-outline-variant shadow-sm">
<div class="flex bg-surface-container-high/30 px-4 pt-3 gap-1">
<button type="button" data-mode="basic" class="px-6 py-3 text-[12px] font-bold tracking-widest text-primary border-b-2 border-primary bg-white/50 rounded-t-lg">THÔNG SỐ CƠ BẢN</button>
<button type="button" data-mode="advanced" class="px-6 py-3 text-[12px] font-bold tracking-widest text-on-surface-variant hover:text-primary transition-colors">THIẾT LẬP NÂNG CAO</button>
</div>
<div class="p-8 flex flex-col gap-6 w-full">
  
  <!-- QUICK PRESETS ROW -->
  <div class="flex flex-col gap-2">
    <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Chọn nhanh cấu hình mẫu (Preset):</label>
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <button type="button" data-preset="compact" class="p-3 text-left rounded-xl border border-outline-variant bg-white hover:bg-surface-container transition-all">
        <span class="block font-bold text-sm text-industrial-navy">Báo cáo gọn</span>
        <span class="block text-[11px] text-on-surface-variant font-medium">Ít mốc hơn, bảng ngắn hơn.</span>
      </button>
      <button type="button" data-preset="daily" class="p-3 text-left rounded-xl border border-outline-variant bg-white hover:bg-surface-container transition-all">
        <span class="block font-bold text-sm text-industrial-navy">Vận hành hằng ngày</span>
        <span class="block text-[11px] text-on-surface-variant font-medium">Cân bằng, khuyên dùng.</span>
      </button>
      <button type="button" data-preset="detailed" class="p-3 text-left rounded-xl border border-outline-variant bg-white hover:bg-surface-container transition-all">
        <span class="block font-bold text-sm text-industrial-navy">Soi kỹ tuyến</span>
        <span class="block text-[11px] text-on-surface-variant font-medium">Giữ nhiều mốc để xem chi tiết.</span>
      </button>
      <button type="button" data-preset="range" class="p-3 text-left rounded-xl border border-outline-variant bg-white hover:bg-surface-container transition-all">
        <span class="block font-bold text-sm text-industrial-navy">Kiểm tra theo đoạn</span>
        <span class="block text-[11px] text-on-surface-variant font-medium">Chỉ phân tích đoạn được chọn.</span>
      </button>
    </div>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
    <!-- BASIC FIELDS -->
    <div class="space-y-2">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Ngưỡng Event</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">dB</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="0.01" type="number" id="threshold" value="0.10"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Chỉ phân tích các sự kiện có suy hao vượt ngưỡng này.</p>
    </div>

    <div class="space-y-2">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Ngưỡng Section Loss</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">dB/km</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" placeholder="Tự động" step="0.01" type="number" id="sectionThreshold"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Cảnh báo đỏ nếu suy hao trung bình vượt ngưỡng thiết lập.</p>
    </div>

    <div class="space-y-2">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Thời gian đo (Duration)</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">Giây</span>
      </div>
      <div class="relative">
        <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="1" type="number" id="durationThreshold" value="15"/>
      </div>
      <p class="text-[11px] text-on-surface-variant font-medium">Đánh dấu không đạt (Fail) nếu thời gian đo thực tế thấp hơn.</p>
    </div>

    <div class="space-y-2">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Dung sai gom cụm</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">Mét</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="1" type="number" id="deviation" value="5"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Khoảng cách tối đa để gộp các điểm suy hao gần nhau.</p>
    </div>

    <div class="space-y-2" id="expectedLengthCard">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Chiều dài tuyến chuẩn</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" placeholder="Ví dụ: 38.800" step="0.001" type="number" id="expectedLength"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Nhập chiều dài thiết kế để đối chiếu kiểm thử.</p>
    </div>

    <div class="space-y-2" id="routeToleranceCard">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Sai số đủ tuyến</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="0.001" type="number" id="routeTolerance" value="0.300"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Dung sai độ lệch chiều dài cho phép.</p>
    </div>

    <div class="space-y-2">
      <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Kiểu file đầu ra</label>
      <select class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" id="outputMode">
        <option value="fastreporter" selected>FastReporter OTDR Cable (Chuẩn FPT)</option>
        <option value="stv">Bảng sự kiện kiểm tra tuyến (STV)</option>
      </select>
      <p class="text-[11px] text-on-surface-variant font-medium">Chọn mẫu định dạng file xuất ra.</p>
    </div>

    <!-- Core inputs: always visible -->
    <div id="stvCoreFields">
      <div class="border border-outline-variant rounded-xl overflow-hidden">
        <div class="px-4 py-2.5 bg-surface-container-high border-b border-outline-variant">
          <span class="text-[11px] font-bold text-industrial-navy uppercase tracking-widest">Thông số Core</span>
        </div>
        <div class="grid grid-cols-2 divide-x divide-outline-variant">
          <div class="p-3 space-y-1.5">
            <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider block" for="stvTotalCore">Tổng core</label>
            <input class="w-full bg-white border border-outline-variant rounded-lg px-3 py-2.5 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" type="number" id="stvTotalCore" min="1" step="1" placeholder="VD: 24"/>
            <p class="text-[10px] text-on-surface-variant leading-tight">Tổng số core cáp. Để trống = tự tính theo số file.</p>
          </div>
          <div class="p-3 space-y-1.5">
            <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider block" for="stvUsedCore">Core sử dụng</label>
            <input class="w-full bg-white border border-outline-variant rounded-lg px-3 py-2.5 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" type="number" id="stvUsedCore" min="0" step="1" placeholder="VD: 4"/>
            <p class="text-[10px] text-on-surface-variant leading-tight">Core đang khai thác. Để trống = tự tính.</p>
          </div>
        </div>
      </div>
    </div>

    <!-- ADVANCED FIELDS (Hidden by default unless advanced tab is active) -->
    <div class="space-y-2" data-level="advanced">
      <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Xuất section theo</label>
      <select class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" id="sectionExportScope">
        <option value="all" selected>Toàn bộ tuyến đo được</option>
        <option value="selected_range">Chỉ đoạn đã chọn (Từ mốc bắt đầu -> kết thúc)</option>
      </select>
      <p class="text-[11px] text-on-surface-variant font-medium">Phạm vi xuất dữ liệu của sheet Sections.</p>
    </div>

    <div class="space-y-2" data-level="advanced" data-role="range-boundary">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Đoạn bắt đầu</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" placeholder="Ví dụ: 38.000" step="0.001" type="number" id="segmentStart"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Điểm đầu phân tích đoạn riêng.</p>
    </div>

    <div class="space-y-2" data-level="advanced" data-role="range-boundary">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Đoạn kết thúc</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" placeholder="Ví dụ: 40.000" step="0.001" type="number" id="segmentEnd"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Điểm cuối phân tích đoạn riêng.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Độ chi tiết bảng Section</label>
      <select class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" id="sectionDetailLevel">
        <option value="maximum">Tối đa (Nhiều mốc sự kiện nhất)</option>
        <option value="balanced" selected>Vừa phải (Khuyên dùng)</option>
        <option value="minimum">Tối thiểu (Chỉ mốc chính)</option>
      </select>
      <p class="text-[11px] text-on-surface-variant font-medium">Quyết định mật độ mốc phân chia.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Sai số gom đoạn</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">m</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="1" type="number" id="sectionMergeTolerance" value="100"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Khoảng cách tối đa gộp mốc gần nhau.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Chiều dài đoạn tối thiểu</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="0.1" type="number" id="sectionMinLength" value="0"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Bỏ qua đoạn chia nhỏ hơn chiều dài này.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Lấy mốc chia đoạn</label>
      <select class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" id="sectionEventSource">
        <option value="all" selected>Tất cả mốc sự kiện (Suy hao + Phản xạ)</option>
        <option value="loss">Chỉ các mốc suy hao</option>
        <option value="reflectance">Chỉ các mốc phản xạ</option>
      </select>
      <p class="text-[11px] text-on-surface-variant font-medium">Sự kiện làm ranh giới mốc đoạn.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Ưu tiên nguồn chia đoạn</label>
      <select class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" id="sectionBoundaryPriority">
        <option value="event" selected>Ưu tiên mốc sự kiện quang</option>
        <option value="preset">Ưu tiên mốc thiết lập trước</option>
      </select>
      <p class="text-[11px] text-on-surface-variant font-medium">Phương án giải quyết xung đột ranh giới.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Cho phép chia nhỏ đoạn</label>
      <select class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" id="sectionAllowSplit">
        <option value="false" selected>Không chia nhỏ (Khuyên dùng)</option>
        <option value="true">Tự động chia nhỏ khi đoạn quá dài</option>
      </select>
      <p class="text-[11px] text-on-surface-variant font-medium">Thêm mốc nhân tạo nếu khoảng cách quá dài.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Sai số so khớp</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">m</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="1" type="number" id="sectionMatchTolerance" value="100"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Dung sai định danh trùng khớp sự kiện.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Cách tính suy hao Section</label>
      <select class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" id="sectionMeasurementMode">
        <option value="fit" selected>Tự động khớp tuyến tính LSA</option>
        <option value="two_point">Phương pháp 2 điểm (Simple 2-Point)</option>
      </select>
      <p class="text-[11px] text-on-surface-variant font-medium">Công thức toán học ước lượng suy hao riêng đoạn.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <div class="flex justify-between items-end">
        <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Ngưỡng ORL đạt</label>
        <span class="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">dB</span>
      </div>
      <input class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="0.1" type="number" id="orlPassThreshold" value="28.0"/>
      <p class="text-[11px] text-on-surface-variant font-medium">Giá trị tối thiểu để kết luận ORL đạt chuẩn.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Nguồn ORL</label>
      <select class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" id="orlSourceMode">
        <option value="auto" selected>Tự động (Ưu tiên ORL đo thật)</option>
        <option value="trace">Lấy từ đồ thị quang</option>
      </select>
      <p class="text-[11px] text-on-surface-variant font-medium">Lựa chọn nguồn dữ liệu ORL gốc để phân tích.</p>
    </div>

    <div class="space-y-2" data-level="advanced">
      <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Khi thiếu ORL đo thật</label>
      <select class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" id="orlMissingPolicy">
        <option value="blank">Để trống</option>
        <option value="reference" selected>Hiện giá trị tham khảo nếu có</option>
        <option value="trace_check">Tự kiểm tra điều kiện ORL từ trace</option>
      </select>
      <p class="text-[11px] text-on-surface-variant font-medium">Phương án giải quyết khi file đo gốc bị thiếu ORL.</p>
    </div>
  </div>

  <!-- Hidden inputs for ORL mapping -->
  <input type="hidden" id="orlAllowLowerBound" value="true" />
  <input type="hidden" id="orlLowerBoundStatus" value="Unknown" />
  <input type="hidden" id="orlPhysicalMode" value="disabled" />
</div></section>
<!-- Action Area -->
<section class="opacity-0 animate-fade-up stagger-4">
<button id="convertBtn" class="group w-full h-20 bg-industrial-navy hover:bg-primary text-white rounded-2xl font-headline-md text-[20px] flex items-center justify-center gap-4 transition-all active:scale-[0.98] shadow-xl shadow-primary/20 btn-pro relative overflow-hidden">
<div class="absolute inset-0 shimmer-effect opacity-20 pointer-events-none"></div>
<span class="material-symbols-outlined text-[32px]">table_view</span>
<span class="tracking-tight">XUẤT BÁO CÁO EXCEL</span>
<span class="material-symbols-outlined text-[20px] opacity-0 group-hover:opacity-100 group-hover:translate-x-2 transition-all">arrow_forward</span>
</button>
<div class="flex items-center justify-center gap-2 mt-4 text-on-surface-variant">
<span class="material-symbols-outlined text-[16px]">verified</span>
<p class="text-[12px] font-bold uppercase tracking-wider">Hệ thống sẵn sàng tạo file theo cấu hình hiện tại</p>
</div>
</section>
</div>

<!-- Export Modal -->
<div id="exportModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] hidden flex items-center justify-center">
    <div class="bg-white rounded-2xl shadow-2xl p-6 w-[90%] max-w-md border border-outline-variant transform scale-95 transition-transform duration-200" id="exportModalContent">
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-headline-md font-bold text-industrial-navy">Thông tin xuất file</h2>
            <button id="closeExportModalBtn" class="text-on-surface-variant hover:text-error transition-colors">
                <span class="material-symbols-outlined">close</span>
            </button>
        </div>
        <div class="space-y-4">
            <div class="space-y-1">
                <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Tên người xuất <span class="text-error">*</span></label>
                <input type="text" id="exporterNameInput" class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" placeholder="Ví dụ: Nguyễn Văn A">
            </div>
            <div class="space-y-1">
                <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Đơn vị <span class="text-error">*</span></label>
                <input type="text" id="exporterUnitInput" class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" placeholder="Ví dụ: INF MN">
            </div>
            <div class="space-y-1">
                <label class="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Tuyến xuất <span class="text-error">*</span></label>
                <input type="text" id="exportRouteInput" class="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" placeholder="Ví dụ: Tuyến số 1">
            </div>
        </div>
        <div class="mt-6 flex justify-end gap-3">
            <button id="cancelExportBtn" class="px-5 py-2.5 rounded-lg text-on-surface-variant font-bold hover:bg-surface-variant transition-colors">Hủy</button>
            <button id="confirmExportBtn" class="px-5 py-2.5 rounded-lg bg-primary text-white font-bold hover:bg-industrial-navy transition-colors flex items-center gap-2 shadow-lg shadow-primary/20">
                <span class="material-symbols-outlined text-[18px]">check_circle</span> Xác nhận
            </button>
        </div>
    </div>
</div>

<!-- History Modal -->
<div id="historyModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] hidden flex items-center justify-center">
    <div class="bg-white rounded-2xl shadow-2xl p-6 w-[95%] max-w-4xl max-h-[85vh] border border-outline-variant flex flex-col" id="historyModalContent">
        <div class="flex justify-between items-center mb-4 shrink-0">
            <h2 class="text-xl font-headline-md font-bold text-industrial-navy flex items-center gap-2">
                <span class="material-symbols-outlined">history</span> Lịch sử xuất báo cáo
            </h2>
            <button id="closeHistoryModalBtn" class="text-on-surface-variant hover:text-error transition-colors">
                <span class="material-symbols-outlined">close</span>
            </button>
        </div>
        <div class="overflow-auto rounded-xl border border-outline-variant">
            <table class="w-full text-left border-collapse">
                <thead class="bg-surface-container text-[12px] uppercase font-bold text-industrial-navy sticky top-0">
                    <tr>
                        <th class="p-4 border-b border-outline-variant">Thời gian</th>
                        <th class="p-4 border-b border-outline-variant">Người xuất</th>
                        <th class="p-4 border-b border-outline-variant">Đơn vị</th>
                        <th class="p-4 border-b border-outline-variant">Tuyến</th>
                    </tr>
                </thead>
                <tbody id="historyTableBody" class="text-sm font-medium text-on-surface">
                    <tr><td colspan="4" class="p-6 text-center text-on-surface-variant">Đang tải dữ liệu...</td></tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
\n</main>
<!-- BottomNavBar (Mobile Only) -->
<nav class="fixed bottom-0 w-full flex justify-around items-center h-16 bg-white/90 backdrop-blur-md z-50 md:hidden border-t border-outline-variant px-4">
<button class="flex flex-col items-center justify-center px-4 text-primary">
<span class="material-symbols-outlined text-[24px] filled-icon">tune</span>
<span class="text-[10px] font-bold uppercase mt-1">Cấu hình</span>
</button>
<button onclick="window.open('/graph', '_blank')" class="flex flex-col items-center justify-center px-4 text-on-surface-variant opacity-50 hover:opacity-100 transition-opacity">
<span class="material-symbols-outlined text-[24px] text-primary">show_chart</span>
<span class="text-[10px] font-bold uppercase mt-1 text-primary">Đồ thị</span>
</button>
<button class="flex flex-col items-center justify-center px-4 text-on-surface-variant opacity-50">
<span class="material-symbols-outlined text-[24px]">history</span>
<span class="text-[10px] font-bold uppercase mt-1">Lịch sử</span>
</button>
</nav>
<!-- Mobile Nav Spacing -->
<div class="h-16 md:hidden"></div>

<!-- Toast Container for Realtime Popups -->
<div id="toastContainer" class="fixed bottom-20 md:bottom-6 right-4 md:right-6 z-[110] flex flex-col gap-2 pointer-events-none w-[90%] max-w-sm"></div>
  <script>

    const dropzone = document.getElementById('dropzone');
    const notifBtn = document.getElementById('notifBtn');
    const notifBadge = document.getElementById('notifBadge');
    const notifDropdown = document.getElementById('notifDropdown');
    const notifList = document.getElementById('notifList');
    const markAllReadBtn = document.getElementById('markAllReadBtn');
    const toastContainer = document.getElementById('toastContainer');

    const fileInput = document.getElementById('fileInput');
    const fileList = document.getElementById('fileList');
    const statusEl = document.getElementById('status');
    const convertBtn = document.getElementById('convertBtn');
    const thresholdEl = document.getElementById('threshold');
    const sectionThresholdEl = document.getElementById('sectionThreshold');
    const durationThresholdEl = document.getElementById('durationThreshold');
    const deviationEl = document.getElementById('deviation');
    const expectedLengthEl = document.getElementById('expectedLength');
    const routeToleranceEl = document.getElementById('routeTolerance');
    const segmentStartEl = document.getElementById('segmentStart');
    const segmentEndEl = document.getElementById('segmentEnd');
    const sectionExportScopeEl = document.getElementById('sectionExportScope');
    const sectionMergeToleranceEl = document.getElementById('sectionMergeTolerance');
    const sectionMinLengthEl = document.getElementById('sectionMinLength');
    const sectionEventSourceEl = document.getElementById('sectionEventSource');
    const sectionBoundaryPriorityEl = document.getElementById('sectionBoundaryPriority');
    const sectionAllowSplitEl = document.getElementById('sectionAllowSplit');
    const sectionMatchToleranceEl = document.getElementById('sectionMatchTolerance');
    const sectionMeasurementModeEl = document.getElementById('sectionMeasurementMode');
    const orlPassThresholdEl = document.getElementById('orlPassThreshold');
    const orlSourceModeEl = document.getElementById('orlSourceMode');
    const orlMissingPolicyEl = document.getElementById('orlMissingPolicy');
    const orlAllowLowerBoundEl = document.getElementById('orlAllowLowerBound');
    const orlLowerBoundStatusEl = document.getElementById('orlLowerBoundStatus');
    const orlPhysicalModeEl = document.getElementById('orlPhysicalMode');
    const outputModeEl = document.getElementById('outputMode');
    const stvTotalCoreEl = document.getElementById('stvTotalCore');
    const stvUsedCoreEl = document.getElementById('stvUsedCore');
    const modeButtons = Array.from(document.querySelectorAll('[data-mode]'));
    const presetButtons = Array.from(document.querySelectorAll('[data-preset]'));
    const advancedCards = Array.from(document.querySelectorAll('[data-level="advanced"]'));
    const rangeCards = Array.from(document.querySelectorAll('[data-role="range-boundary"]'));
    const STORAGE_KEY = 'fpt-telecom-trace-settings-stitch-v2';
    let parameterMode = 'basic';
    let lastPreset = '';
    let lastOrlPreset = '';

    const fieldMap = {
      threshold: thresholdEl, sectionThreshold: sectionThresholdEl, durationThreshold: durationThresholdEl, deviation: deviationEl, expectedLength: expectedLengthEl, routeTolerance: routeToleranceEl,
      segmentStart: segmentStartEl, segmentEnd: segmentEndEl, sectionExportScope: sectionExportScopeEl, sectionMergeTolerance: sectionMergeToleranceEl,
      sectionMinLength: sectionMinLengthEl, sectionEventSource: sectionEventSourceEl, sectionBoundaryPriority: sectionBoundaryPriorityEl,
      sectionAllowSplit: sectionAllowSplitEl, sectionMatchTolerance: sectionMatchToleranceEl, sectionMeasurementMode: sectionMeasurementModeEl,
      orlPassThreshold: orlPassThresholdEl, orlSourceMode: orlSourceModeEl, orlMissingPolicy: orlMissingPolicyEl, orlAllowLowerBound: orlAllowLowerBoundEl,
      orlLowerBoundStatus: orlLowerBoundStatusEl, orlPhysicalMode: orlPhysicalModeEl,
      outputMode: outputModeEl,
      sectionDetailLevel: document.getElementById('sectionDetailLevel')
    };

    function setParameterMode(mode, shouldSave = true) {
      parameterMode = mode === 'advanced' ? 'advanced' : 'basic';
      const showAdvanced = parameterMode === 'advanced';
      advancedCards.forEach(card => card.classList.toggle('advanced-hidden', !showAdvanced));
      modeButtons.forEach(btn => {
        const isActive = btn.dataset.mode === parameterMode;
        btn.className = isActive 
          ? "px-6 py-3 text-[12px] font-bold tracking-widest text-primary border-b-2 border-primary bg-white/50 rounded-t-lg"
          : "px-6 py-3 text-[12px] font-bold tracking-widest text-on-surface-variant hover:text-primary transition-colors";
      });
      if (shouldSave) saveSettings();
    }

    function applyOrlMissingPolicy() {
      const policy = (orlMissingPolicyEl && orlMissingPolicyEl.value) || 'reference';
      if (policy === 'blank') {
        orlAllowLowerBoundEl.value = 'false';
        orlLowerBoundStatusEl.value = 'Unknown';
        orlPhysicalModeEl.value = 'disabled';
      } else if (policy === 'trace_check') {
        orlAllowLowerBoundEl.value = 'true';
        orlLowerBoundStatusEl.value = 'Unknown';
        orlPhysicalModeEl.value = 'diagnostic';
      } else {
        orlAllowLowerBoundEl.value = 'true';
        orlLowerBoundStatusEl.value = 'Unknown';
        orlPhysicalModeEl.value = 'disabled';
      }
    }

    function collectSettings() {
      applyOrlMissingPolicy();
      return Object.fromEntries(Object.entries(fieldMap).map(([k, el]) => [k, el ? el.value : '']));
    }

    function saveSettings() {
      const payload = collectSettings();
      payload.__parameterMode = parameterMode;
      payload.__lastPreset = lastPreset;
      payload.__lastOrlPreset = lastOrlPreset;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      updatePresetVisuals();
    }

    function loadSettings() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        Object.entries(fieldMap).forEach(([k, el]) => {
          if (el && parsed[k] !== undefined && parsed[k] !== null) el.value = parsed[k];
        });
        if (!parsed.orlMissingPolicy && orlMissingPolicyEl) {
          if (String(parsed.orlPhysicalMode || '').toLowerCase() === 'diagnostic') orlMissingPolicyEl.value = 'trace_check';
          else if (String(parsed.orlAllowLowerBound || '').toLowerCase() === 'false') orlMissingPolicyEl.value = 'blank';
          else orlMissingPolicyEl.value = 'reference';
        }
        applyOrlMissingPolicy();
        setParameterMode(parsed.__parameterMode || 'basic', false);
        lastPreset = parsed.__lastPreset || '';
        lastOrlPreset = parsed.__lastOrlPreset || '';
        updatePresetVisuals();
      } catch (err) {
        console.warn('Lỗi load settings:', err);
      }
    }

    function applyPreset(preset) {
      lastPreset = preset;
      if (preset === 'compact') {
        if (thresholdEl) thresholdEl.value = '0.50';
        if (sectionThresholdEl) sectionThresholdEl.value = '';
        if (deviationEl) deviationEl.value = '100';
        if (fieldMap.sectionDetailLevel) fieldMap.sectionDetailLevel.value = 'minimum';
        if (sectionMergeToleranceEl) sectionMergeToleranceEl.value = '200';
        if (sectionMinLengthEl) sectionMinLengthEl.value = '0.5';
        if (sectionAllowSplitEl) sectionAllowSplitEl.value = 'false';
        if (sectionExportScopeEl) sectionExportScopeEl.value = 'all';
      } else if (preset === 'daily') {
        if (thresholdEl) thresholdEl.value = '0.50';
        if (sectionThresholdEl) sectionThresholdEl.value = '';
        if (deviationEl) deviationEl.value = '100';
        if (fieldMap.sectionDetailLevel) fieldMap.sectionDetailLevel.value = 'balanced';
        if (sectionMergeToleranceEl) sectionMergeToleranceEl.value = '100';
        if (sectionMinLengthEl) sectionMinLengthEl.value = '0';
        if (sectionAllowSplitEl) sectionAllowSplitEl.value = 'false';
        if (sectionExportScopeEl) sectionExportScopeEl.value = 'all';
      } else if (preset === 'detailed') {
        if (thresholdEl) thresholdEl.value = '0.30';
        if (sectionThresholdEl) sectionThresholdEl.value = '0.500';
        if (deviationEl) deviationEl.value = '50';
        if (fieldMap.sectionDetailLevel) fieldMap.sectionDetailLevel.value = 'maximum';
        if (sectionMergeToleranceEl) sectionMergeToleranceEl.value = '50';
        if (sectionMinLengthEl) sectionMinLengthEl.value = '0';
        if (sectionAllowSplitEl) sectionAllowSplitEl.value = 'true';
        if (sectionExportScopeEl) sectionExportScopeEl.value = 'all';
      } else if (preset === 'range') {
        if (thresholdEl) thresholdEl.value = '0.30';
        if (sectionThresholdEl) sectionThresholdEl.value = '';
        if (deviationEl) deviationEl.value = '100';
        if (fieldMap.sectionDetailLevel) fieldMap.sectionDetailLevel.value = 'maximum';
        if (sectionMergeToleranceEl) sectionMergeToleranceEl.value = '50';
        if (sectionMinLengthEl) sectionMinLengthEl.value = '0';
        if (sectionAllowSplitEl) sectionAllowSplitEl.value = 'false';
        if (sectionExportScopeEl) sectionExportScopeEl.value = 'selected_range';
      }
      syncHiddenSectionControls();
      saveSettings();
    }

    function syncHiddenSectionControls() {
      const scope = sectionExportScopeEl ? sectionExportScopeEl.value : 'all';
      const showRange = (scope === 'selected_range');
      rangeCards.forEach(card => card.style.display = showRange ? '' : 'none');
    }

    function updatePresetVisuals() {
      presetButtons.forEach(btn => {
        const isSel = btn.dataset.preset === lastPreset;
        btn.classList.toggle('border-primary', isSel);
        btn.classList.toggle('border-2', isSel);
        btn.classList.toggle('bg-primary/5', isSel);
      });
    }

    let selectedFiles = [];
    async function saveFilesToIndexedDB(files) {
      try {
        const openDb = () => {
          return new Promise((resolve, reject) => {
            const request = indexedDB.open('otdr_shared_files_db', 1);
            request.onupgradeneeded = (e) => {
              const db = request.result;
              if (!db.objectStoreNames.contains('shared_files')) {
                db.createObjectStore('shared_files', { keyPath: 'id' });
              }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
        };

        if (!files || files.length === 0) {
          const db = await openDb();
          const transaction = db.transaction('shared_files', 'readwrite');
          const store = transaction.objectStore('shared_files');
          store.delete(1);
          return;
        }

        const fileDataPromises = Array.from(files).map(file => {
          return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => {
              resolve({ name: file.name, data: reader.result });
            };
            reader.readAsArrayBuffer(file);
          });
        });

        const fileDataList = await Promise.all(fileDataPromises);

        const db = await openDb();
        const transaction = db.transaction('shared_files', 'readwrite');
        const store = transaction.objectStore('shared_files');
        store.put({ id: 1, files: fileDataList });
      } catch (err) {
        console.error('Error saving files to IndexedDB:', err);
      }
    }

    const allowed = ['.msor', '.sor', '.trc'];

    function setStatus(message, kind = 'info') {
      if (!statusEl) return;
      statusEl.textContent = message;
      statusEl.classList.remove('hidden');
      statusEl.className = 'status mt-2 p-4 rounded-xl text-sm border font-medium';
      if (kind === 'error') {
        statusEl.classList.add('bg-status-fail/10', 'border-status-fail/30', 'text-status-fail');
      } else if (kind === 'success') {
        statusEl.classList.add('bg-status-pass/10', 'border-status-pass/30', 'text-status-pass');
      } else {
        statusEl.classList.add('bg-surface-container', 'border-outline-variant', 'text-on-surface-variant');
      }
    }

    function renderFiles() {
      if (!selectedFiles.length) {
         fileList.innerHTML = '<div class="file-empty text-center text-sm text-on-surface-variant">Chưa chọn file nguồn.</div>';
         return;
      }
      fileList.innerHTML = selectedFiles.map((f, idx) => `
        <div class="file-item flex justify-between items-center bg-white border border-outline-variant p-3 rounded-lg">
          <span class="file-name text-sm text-industrial-navy truncate pr-4 font-semibold" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
          <button type="button" class="file-remove-btn w-6 h-6 flex items-center justify-center rounded-full hover:bg-surface-container text-on-surface-variant hover:text-status-fail transition-all" data-file-index="${idx}" title="Xóa file này khỏi danh sách">×</button>
        </div>
      `).join('') + '<div class="file-actions-hint text-xs text-on-surface-variant mt-1 font-medium">Nếu không muốn xử lý file nào, hãy bấm × để loại bỏ trước khi xuất Excel.</div>';
      
      fileList.querySelectorAll('[data-file-index]').forEach(btn => {
        btn.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          removeSelectedFile(Number(btn.dataset.fileIndex || '0'));
        });
      });
    }

    function removeSelectedFile(index) {
      if (!Number.isInteger(index) || index < 0 || index >= selectedFiles.length) return;
      const removed = selectedFiles[index]?.name || '';
      selectedFiles.splice(index, 1);
      if (!selectedFiles.length && fileInput) fileInput.value = '';
      renderFiles();
      setStatus(
        selectedFiles.length
          ? `Đã bỏ ${removed}. Còn ${selectedFiles.length} file sẵn sàng xử lý.`
          : 'Đã xóa hết file khỏi danh sách.',
        selectedFiles.length ? 'success' : 'info'
      );
      saveFilesToIndexedDB(selectedFiles);
    }

    function setFiles(fileListObject) {
      selectedFiles = Array.from(fileListObject).filter(f => allowed.some(ext => f.name.toLowerCase().endsWith(ext)));
      renderFiles();
      setStatus(
        selectedFiles.length
          ? `${selectedFiles.length} file đã sẵn sàng. Bấm "Xuất file Excel" để tạo kết quả.`
          : 'Không tìm thấy file .MSOR / .SOR / .TRC hợp lệ.',
        selectedFiles.length ? 'success' : 'error'
      );
      saveFilesToIndexedDB(selectedFiles);
    }


    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }

    async function buildAnalysisForm() {
      const form = new FormData();
      if (selectedFiles.length > 0) {
        const zip = new JSZip();
        for (const file of selectedFiles) {
          zip.file(file.name, file);
        }
        const zipBlob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 6 } });
        form.append('files', zipBlob, 'batch.zip');
      }
      form.append('threshold_db', thresholdEl ? thresholdEl.value : '0.5');
      form.append('section_threshold_db', sectionThresholdEl ? sectionThresholdEl.value : '');
      form.append('duration_threshold_s', durationThresholdEl ? durationThresholdEl.value : '30');
      form.append('deviation_m', deviationEl ? deviationEl.value : '100');
      form.append('expected_route_km', expectedLengthEl ? expectedLengthEl.value : '');
      form.append('graph_reach_tolerance_km', routeToleranceEl ? routeToleranceEl.value : '0.300');
      form.append('event_shortfall_tolerance_km', routeToleranceEl ? routeToleranceEl.value : '0.300');
      form.append('segment_start_km', segmentStartEl ? segmentStartEl.value : '');
      form.append('segment_end_km', segmentEndEl ? segmentEndEl.value : '');
      form.append('section_export_scope', sectionExportScopeEl ? sectionExportScopeEl.value : 'all');
      form.append('section_merge_tolerance_m', sectionMergeToleranceEl ? sectionMergeToleranceEl.value : '100');
      form.append('section_min_length_km', sectionMinLengthEl ? sectionMinLengthEl.value : '0');
      form.append('section_event_source', sectionEventSourceEl ? sectionEventSourceEl.value : 'all');
      form.append('section_boundary_priority', sectionBoundaryPriorityEl ? sectionBoundaryPriorityEl.value : 'event');
      form.append('section_allow_split', sectionAllowSplitEl ? sectionAllowSplitEl.value : 'false');
      form.append('section_match_tolerance_m', sectionMatchToleranceEl ? sectionMatchToleranceEl.value : '100');
      form.append('section_measurement_mode', sectionMeasurementModeEl ? sectionMeasurementModeEl.value : 'fit');
      form.append('orl_pass_threshold_db', orlPassThresholdEl ? orlPassThresholdEl.value : '28.0');
      form.append('orl_source_mode', orlSourceModeEl ? orlSourceModeEl.value : 'auto');
      form.append('orl_missing_policy', orlMissingPolicyEl ? orlMissingPolicyEl.value : 'reference');
      form.append('orl_allow_lower_bound', orlAllowLowerBoundEl ? orlAllowLowerBoundEl.value : 'true');
      form.append('orl_lower_bound_status', orlLowerBoundStatusEl ? orlLowerBoundStatusEl.value : 'Unknown');
      form.append('orl_physical_mode', orlPhysicalModeEl ? orlPhysicalModeEl.value : 'disabled');
      form.append('output_mode', outputModeEl ? outputModeEl.value : 'fastreporter');
      form.append('stv_total_core', stvTotalCoreEl ? stvTotalCoreEl.value : '');
      form.append('stv_used_core', stvUsedCoreEl ? stvUsedCoreEl.value : '');
      return form;
    }

    function validateFormState() {
      if (expectedLengthEl && expectedLengthEl.value.trim()) {
        const val = parseFloat(expectedLengthEl.value.trim());
        if (isNaN(val) || val <= 0) return 'Chiều dài tuyến chuẩn phải là một số thực dương lớn hơn 0.';
      }
      const scope = sectionExportScopeEl ? sectionExportScopeEl.value : 'all';
      if (scope === 'selected_range') {
        const start = segmentStartEl ? segmentStartEl.value.trim() : '';
        const end = segmentEndEl ? segmentEndEl.value.trim() : '';
        if (!start || !end) return 'Khi chọn xuất section theo đoạn đã chọn, cần nhập đủ Đoạn bắt đầu và Đoạn kết thúc.';
        const startVal = parseFloat(start);
        const endVal = parseFloat(end);
        if (isNaN(startVal) || startVal < 0) return 'Đoạn bắt đầu phải là số thực không âm.';
        if (isNaN(endVal) || endVal <= startVal) return 'Đoạn kết thúc phải lớn hơn Đoạn bắt đầu.';
      }
      return '';
    }

    if (dropzone) {
      dropzone.addEventListener('click', () => fileInput && fileInput.click());
      dropzone.addEventListener('dragenter', (e) => { e.preventDefault(); dropzone.classList.add('bg-primary/5'); });
      dropzone.addEventListener('dragover', (e) => { e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'; dropzone.classList.add('bg-primary/5'); });
      dropzone.addEventListener('dragleave', () => dropzone.classList.remove('bg-primary/5'));
      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('bg-primary/5');
        const dt = e.dataTransfer;
        if (!dt) {
          setStatus('Không đọc được dữ liệu kéo-thả. Hãy chọn file trực tiếp.', 'error');
          return;
        }
        setFiles(dt.files || []);
      });
    }

    if (fileInput) {
      fileInput.addEventListener('change', (e) => setFiles(e.target.files));
    }

    const exportModal = document.getElementById('exportModal');
    const exportModalContent = document.getElementById('exportModalContent');
    const closeExportModalBtn = document.getElementById('closeExportModalBtn');
    const cancelExportBtn = document.getElementById('cancelExportBtn');
    const confirmExportBtn = document.getElementById('confirmExportBtn');
    const exporterNameInput = document.getElementById('exporterNameInput');
    const exporterUnitInput = document.getElementById('exporterUnitInput');
    const exportRouteInput = document.getElementById('exportRouteInput');
    
    const historyModal = document.getElementById('historyModal');
    const closeHistoryModalBtn = document.getElementById('closeHistoryModalBtn');
    const historyTableBody = document.getElementById('historyTableBody');
    
    document.querySelectorAll('button').forEach(btn => {
        if (btn.innerText.toLowerCase().includes('lịch sử')) {
            btn.addEventListener('click', openHistoryModal);
        }
    });

    const savedName = localStorage.getItem('otdr_exporter_name') || '';
    const savedUnit = localStorage.getItem('otdr_exporter_unit') || '';
    if(exporterNameInput) exporterNameInput.value = savedName;
    if(exporterUnitInput) exporterUnitInput.value = savedUnit;

    function closeExportModal() {
        if(exportModalContent) exportModalContent.classList.add('scale-95');
        setTimeout(() => { if(exportModal) exportModal.classList.add('hidden'); }, 200);
    }
    if(closeExportModalBtn) closeExportModalBtn.addEventListener('click', closeExportModal);
    if(cancelExportBtn) cancelExportBtn.addEventListener('click', closeExportModal);

    async function openHistoryModal() {
        if(historyModal) historyModal.classList.remove('hidden');
        if(historyTableBody) historyTableBody.innerHTML = '<tr><td colspan="4" class="p-6 text-center text-on-surface-variant animate-pulse">Đang tải dữ liệu...</td></tr>';
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            if (data.status === 'success') {
                if (data.data.length === 0) {
                    historyTableBody.innerHTML = '<tr><td colspan="4" class="p-6 text-center text-on-surface-variant">Chưa có lịch sử xuất file.</td></tr>';
                } else {
                    historyTableBody.innerHTML = data.data.map(item => `
                        <tr class="hover:bg-surface-container-low transition-colors border-b border-outline-variant/30 last:border-0">
                            <td class="p-4 font-mono-data text-xs">${item.export_time}</td>
                            <td class="p-4 text-industrial-navy font-bold">${item.exporter_name}</td>
                            <td class="p-4"><span class="px-2 py-1 bg-primary/10 text-primary text-xs rounded font-bold">${item.unit}</span></td>
                            <td class="p-4">${item.route_name}</td>
                        </tr>
                    `).join('');
                }
            } else {
                throw new Error(data.detail);
            }
        } catch(err) {
            if(historyTableBody) historyTableBody.innerHTML = `<tr><td colspan="4" class="p-6 text-center text-error font-bold">Lỗi tải lịch sử: ${err.message}</td></tr>`;
        }
    }
    if(closeHistoryModalBtn) closeHistoryModalBtn.addEventListener('click', () => {
        if(historyModal) historyModal.classList.add('hidden');
    });

    if (convertBtn) {
      convertBtn.addEventListener('click', () => {
        if (!selectedFiles.length) {
          setStatus('Chưa chọn file nguồn để xử lý.', 'error');
          return;
        }
        const validationMessage = validateFormState();
        if (validationMessage) {
          setStatus(validationMessage, 'error');
          return;
        }
        exportModal.classList.remove('hidden');
        setTimeout(() => exportModalContent.classList.remove('scale-95'), 10);
      });
    }

    if (confirmExportBtn) {
      confirmExportBtn.addEventListener('click', async () => {
        const name = exporterNameInput.value.trim();
        const unit = exporterUnitInput.value.trim();
        const route = exportRouteInput.value.trim();
        if (!name || !unit || !route) {
            alert('Vui lòng nhập đầy đủ Tên, Đơn vị và Tuyến xuất!');
            return;
        }
        localStorage.setItem('otdr_exporter_name', name);
        localStorage.setItem('otdr_exporter_unit', unit);
        closeExportModal();

        setStatus('Đang gửi file lên server xử lý...', 'info');
        convertBtn.disabled = true;
        const form = await buildAnalysisForm();
        form.append('exporter_name', name);
        form.append('unit', unit);
        form.append('route_name', route);
        
        try {
          const response = await fetch('/convert', {
            method: 'POST',
            body: form
          });
          if (!response.ok) {
            const errBody = await response.json().catch(() => ({ detail: 'Lỗi không xác định từ máy chủ.' }));
            throw new Error(errBody.detail || `Lỗi kết nối HTTP: ${response.status}`);
          }
          const blob = await response.blob();
          const disp = response.headers.get('Content-Disposition');
          let filename = 'FastReporter_Output.xlsx';
          if (disp && disp.includes('filename=')) {
            const parts = disp.split('filename=');
            if (parts.length > 1) filename = parts[1].replace(/"/g, '').trim();
          }
          const link = document.createElement('a');
          link.href = window.URL.createObjectURL(blob);
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          setStatus(`Xuất file thành công! Đã tải về tệp "${filename}"`, 'success');
        } catch (err) {
          console.error(err);
          setStatus(`Lỗi xử lý file: ${err.message}`, 'error');
        } finally {
          convertBtn.disabled = false;
        }
      });
    }

    // Bind settings elements to auto-save and update
    Object.values(fieldMap).forEach(el => {
      if (el) {
        el.addEventListener('change', () => {
          if (el !== fieldMap.sectionDetailLevel) lastPreset = '';
          if (el === sectionMergeToleranceEl) syncHiddenSectionControls();
          applyOrlMissingPolicy();
          saveSettings();
        });
      }
    });

    modeButtons.forEach(btn => btn.addEventListener('click', () => setParameterMode(btn.dataset.mode)));
    presetButtons.forEach(btn => btn.addEventListener('click', () => applyPreset(btn.dataset.preset)));

    // Realtime Notifications & Route Export Counter Logic
    let notifications = [];
    let isNotifOpen = false;

    async function fetchNotifications() {
      try {
        const res = await fetch('/api/notifications');
        if (!res.ok) return;
        const json = await res.json();
        if (json.status === 'success' && json.data) {
          const data = json.data;
          notifications = data;
          
          let lastSeenId = parseInt(localStorage.getItem('otdr_last_seen_id') || '0');
          let lastReadId = parseInt(localStorage.getItem('otdr_last_read_id') || '0');
          
          let newNotifications = data.filter(n => n.id > lastSeenId);
          
          if (newNotifications.length > 0) {
            newNotifications.sort((a, b) => a.id - b.id);
            newNotifications.forEach(n => {
              showToastNotification(n.message);
            });
            const maxId = Math.max(...newNotifications.map(n => n.id));
            localStorage.setItem('otdr_last_seen_id', maxId.toString());
          }
          
          renderNotificationList(data, lastReadId);
          
          let unreadCount = data.filter(n => n.id > lastReadId).length;
          if (unreadCount > 0) {
            if (notifBadge) {
              notifBadge.innerText = unreadCount;
              notifBadge.classList.remove('hidden');
            }
          } else {
            if (notifBadge) notifBadge.classList.add('hidden');
          }
        }
      } catch (err) {
        console.error('Error fetching notifications:', err);
      }
    }

    function renderNotificationList(data, lastReadId) {
      if (!notifList) return;
      if (data.length === 0) {
        notifList.innerHTML = `<div class="p-4 text-center text-xs text-on-surface-variant">Không có thông báo mới</div>`;
        return;
      }
      
      notifList.innerHTML = data.map(n => {
        const isUnread = n.id > lastReadId;
        const bgClass = isUnread ? 'bg-primary-fixed/20' : 'bg-transparent';
        const indicator = isUnread ? '<span class="w-2 h-2 rounded-full bg-primary shrink-0"></span>' : '';
        return `
          <div class="p-3.5 flex gap-3 items-start hover:bg-surface-variant transition-colors ${bgClass}">
            <div class="p-1.5 rounded-lg bg-primary/10 text-primary shrink-0">
              <span class="material-symbols-outlined text-[18px]">table_view</span>
            </div>
            <div class="flex-1 flex flex-col gap-0.5 min-w-0">
              <p class="text-xs font-semibold text-on-surface leading-normal break-words">${n.message}</p>
              <span class="text-[10px] text-on-surface-variant font-mono-data">${n.export_time}</span>
            </div>
            ${indicator}
          </div>
        `;
      }).join('');
    }

    function showToastNotification(message) {
      if (!toastContainer) return;
      const toast = document.createElement('div');
      toast.className = 'pointer-events-auto bg-white/95 backdrop-blur-md border border-outline-variant p-4 rounded-xl shadow-2xl flex gap-3 items-start animate-fade-up max-w-sm w-full';
      toast.innerHTML = `
        <div class="p-2 rounded-lg bg-primary text-white shrink-0">
          <span class="material-symbols-outlined text-[20px]">notifications_active</span>
        </div>
        <div class="flex-1 min-w-0">
          <h4 class="text-xs font-bold text-industrial-navy uppercase tracking-wider mb-1">Xuất tuyến realtime</h4>
          <p class="text-xs font-medium text-on-surface-variant leading-relaxed break-words">${message}</p>
        </div>
        <button class="text-on-surface-variant hover:text-error shrink-0" onclick="this.parentElement.remove()">
          <span class="material-symbols-outlined text-[16px]">close</span>
        </button>
      `;
      toastContainer.appendChild(toast);
      
      setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2', 'transition-all', 'duration-300');
        setTimeout(() => toast.remove(), 300);
      }, 5000);
    }

    if (notifBtn) {
      notifBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        isNotifOpen = !isNotifOpen;
        if (notifDropdown) notifDropdown.classList.toggle('hidden', !isNotifOpen);
        
        if (isNotifOpen && notifications.length > 0) {
          const maxId = Math.max(...notifications.map(n => n.id));
          localStorage.setItem('otdr_last_read_id', maxId.toString());
          if (notifBadge) notifBadge.classList.add('hidden');
          renderNotificationList(notifications, maxId);
        }
      });
    }

    if (markAllReadBtn) {
      markAllReadBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (notifications.length > 0) {
          const maxId = Math.max(...notifications.map(n => n.id));
          localStorage.setItem('otdr_last_read_id', maxId.toString());
          if (notifBadge) notifBadge.classList.add('hidden');
          renderNotificationList(notifications, maxId);
        }
      });
    }

    document.addEventListener('click', (e) => {
      if (notifDropdown && !notifDropdown.contains(e.target) && notifBtn && !notifBtn.contains(e.target)) {
        isNotifOpen = false;
        notifDropdown.classList.add('hidden');
      }
    });

    // Start polling
    fetchNotifications();
    setInterval(fetchNotifications, 5000);

    loadSettings();
    syncHiddenSectionControls();

  </script>
</body></html>"""


@app.get('/', response_class=HTMLResponse)
async def home() -> HTMLResponse:
    return HTMLResponse(content=HTML_PAGE)

@app.post('/api/blob-input')
async def create_blob_input(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail='Danh sách file tải lên không hợp lệ.',
        ) from exc

    raw_files = body.get('files') if isinstance(body, dict) else None
    if not isinstance(raw_files, list) or not raw_files:
        raise HTTPException(
            status_code=400,
            detail='Cần ít nhất một file đo kiểm hợp lệ.',
        )

    candidates: list[tuple[str, int, str]] = []
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        original_name = item.get('name')
        size = item.get('size')
        if (
            not isinstance(original_name, str)
            or not original_name
            or os.path.basename(original_name.replace('\\', '/')) != original_name
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
        ):
            continue
        extension = os.path.splitext(original_name)[1].lower()
        if extension in SUPPORTED_INPUT_EXTENSIONS:
            candidates.append((original_name, size, extension))

    selected_extension = next(
        (
            extension
            for extension in INPUT_EXTENSION_PRIORITY
            if any(item[2] == extension for item in candidates)
        ),
        None,
    )
    if selected_extension is None:
        raise HTTPException(
            status_code=400,
            detail='Không có file .sor, .msor hoặc .trc hợp lệ.',
        )

    selected = [
        item for item in candidates if item[2] == selected_extension
    ]
    total_size = sum(item[1] for item in selected)
    if total_size > DEFAULT_MAX_DOWNLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f'Tổng dung lượng file vượt quá giới hạn '
                f'{DEFAULT_MAX_DOWNLOAD_BYTES} byte.'
            ),
        )

    upload_id = str(uuid4())
    files = [
        {
            'original_name': original_name,
            'pathname': build_input_file_path(
                upload_id,
                index,
                original_name,
            ),
            'size': size,
        }
        for index, (original_name, size, _extension) in enumerate(
            selected,
            start=1,
        )
    ]
    return JSONResponse(
        {
            "upload_id": upload_id,
            "selected_extension": selected_extension,
            "files": files,
            "ignored_count": len(raw_files) - len(selected),
            "maximum_total_size_in_bytes": DEFAULT_MAX_DOWNLOAD_BYTES,
        }
    )


def _record_export_history(
    exporter_name: str,
    unit: str,
    route_name: str,
) -> None:
    readable_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            '''
                INSERT INTO export_history (
                    exporter_name,
                    unit,
                    route_name,
                    export_time
                )
                VALUES (?, ?, ?, ?)
            ''',
            (exporter_name, unit, route_name, readable_time),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"Lỗi ghi lịch sử: {exc}")


def _build_export_response(
    payload: Iterable[tuple[str, bytes]],
    *,
    threshold_db: float,
    section_threshold_db: str,
    duration_threshold_s: str,
    deviation_m: float,
    expected_route_km: str,
    jumper_excluded_m: float,
    graph_reach_tolerance_km: float,
    event_shortfall_tolerance_km: float,
    overlength_tolerance_km: float,
    segment_start_km: str,
    segment_end_km: str,
    section_export_scope: str,
    section_merge_tolerance_m: float,
    section_min_length_km: float,
    section_event_source: str,
    section_boundary_priority: str,
    section_allow_split: str,
    section_match_tolerance_m: float,
    section_measurement_mode: str,
    orl_pass_threshold_db: float,
    orl_source_mode: str,
    orl_missing_policy: str,
    orl_allow_lower_bound: str,
    orl_lower_bound_status: str,
    orl_physical_mode: str,
    output_mode: str,
    stv_total_core: str,
    stv_used_core: str,
) -> Response:
    expected_route_value = None
    if expected_route_km.strip():
        expected_route_value = float(expected_route_km.strip())

    segment_start_value = None
    segment_end_value = None
    if segment_start_km.strip():
        segment_start_value = float(segment_start_km.strip())
    if segment_end_km.strip():
        segment_end_value = float(segment_end_km.strip())

    if section_export_scope == 'selected_range':
        if segment_start_value is None or segment_end_value is None:
            raise HTTPException(
                status_code=400,
                detail='Khi chọn xuất section theo đoạn đã chọn, cần nhập đủ Đoạn bắt đầu và Đoạn kết thúc.',
            )
        if segment_end_value <= segment_start_value:
            raise HTTPException(
                status_code=400,
                detail='Đoạn kết thúc phải lớn hơn Đoạn bắt đầu.',
            )
    else:
        if (segment_start_value is None) ^ (segment_end_value is None):
            segment_start_value = None
            segment_end_value = None
        elif (
            segment_start_value is not None
            and segment_end_value is not None
            and segment_end_value <= segment_start_value
        ):
            raise HTTPException(
                status_code=400,
                detail='Đoạn kết thúc phải lớn hơn Đoạn bắt đầu nếu muốn phân tích thêm một đoạn riêng.',
            )

    policy = str(orl_missing_policy or '').strip().lower()
    if policy in {'blank', 'empty', 'none', 'off', 'false'}:
        derived_orl_allow_lower_bound = False
        derived_orl_lower_bound_status = 'Unknown'
        derived_orl_physical_mode = 'disabled'
    elif policy in {'trace_check', 'trace', 'diagnostic', 'auto_trace'}:
        derived_orl_allow_lower_bound = True
        derived_orl_lower_bound_status = 'Unknown'
        derived_orl_physical_mode = 'diagnostic'
    elif policy in {'reference', 'show_reference', 'lower_bound', 'metadata'}:
        derived_orl_allow_lower_bound = True
        derived_orl_lower_bound_status = 'Unknown'
        derived_orl_physical_mode = 'disabled'
    else:
        derived_orl_allow_lower_bound = str(orl_allow_lower_bound).lower() in {
            '1',
            'true',
            'yes',
            'on',
        }
        derived_orl_lower_bound_status = orl_lower_bound_status or 'Unknown'
        derived_orl_physical_mode = orl_physical_mode or 'disabled'

    section_threshold_value = None
    if section_threshold_db.strip():
        section_threshold_value = float(section_threshold_db.strip())

    duration_threshold_value = None
    if duration_threshold_s.strip():
        duration_threshold_value = float(duration_threshold_s.strip())

    stv_total_core_value = None
    if stv_total_core.strip():
        try:
            stv_total_core_value = int(float(stv_total_core.strip()))
        except ValueError:
            pass

    stv_used_core_value = None
    if stv_used_core.strip():
        try:
            stv_used_core_value = int(float(stv_used_core.strip()))
        except ValueError:
            pass

    workbook = build_workbook_from_uploads(
        payload,
        threshold_db=threshold_db,
        section_threshold_db=section_threshold_value,
        duration_threshold_s=duration_threshold_value,
        deviation_m=deviation_m,
        expected_route_km=expected_route_value,
        jumper_excluded_m=jumper_excluded_m,
        graph_reach_tolerance_km=graph_reach_tolerance_km,
        event_shortfall_tolerance_km=event_shortfall_tolerance_km,
        overlength_tolerance_km=overlength_tolerance_km,
        segment_start_km=segment_start_value,
        segment_end_km=segment_end_value,
        section_export_scope=section_export_scope,
        section_merge_tolerance_m=section_merge_tolerance_m,
        section_min_length_km=section_min_length_km,
        section_event_source=section_event_source,
        section_boundary_priority=section_boundary_priority,
        section_allow_split=str(section_allow_split).lower() in {
            '1',
            'true',
            'yes',
            'on',
        },
        section_match_tolerance_m=section_match_tolerance_m,
        section_measurement_mode=section_measurement_mode,
        orl_pass_threshold_db=orl_pass_threshold_db,
        orl_source_mode=orl_source_mode,
        orl_allow_lower_bound=derived_orl_allow_lower_bound,
        orl_lower_bound_status=derived_orl_lower_bound_status,
        orl_physical_mode=derived_orl_physical_mode,
        output_mode=output_mode,
        stv_total_core=stv_total_core_value,
        stv_used_core=stv_used_core_value,
    )
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    prefix = 'Bang_su_kien' if str(output_mode).lower() == 'stv' else 'FastReporter'
    filename = f'{prefix}_{timestamp}.xlsx'
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return Response(
        content=workbook.getvalue(),
        media_type=XLSX_CONTENT_TYPE,
        headers=headers,
    )


@app.post('/convert')
async def convert(
    files: list[UploadFile] = File(...),
    threshold_db: float = Form(0.5),
    section_threshold_db: str = Form(''),
    duration_threshold_s: str = Form(''),
    deviation_m: float = Form(100.0),
    expected_route_km: str = Form(''),
    jumper_excluded_m: float = Form(0.0),
    graph_reach_tolerance_km: float = Form(0.030),
    event_shortfall_tolerance_km: float = Form(0.500),
    overlength_tolerance_km: float = Form(0.500),
    segment_start_km: str = Form(''),
    segment_end_km: str = Form(''),
    section_export_scope: str = Form('all'),
    section_merge_tolerance_m: float = Form(100.0),
    section_min_length_km: float = Form(0.0),
    section_event_source: str = Form('all'),
    section_boundary_priority: str = Form('event'),
    section_allow_split: str = Form('false'),
    section_match_tolerance_m: float = Form(100.0),
    section_measurement_mode: str = Form('fit'),
    orl_pass_threshold_db: float = Form(28.0),
    orl_source_mode: str = Form('auto'),
    orl_missing_policy: str = Form('reference'),
    orl_allow_lower_bound: str = Form('true'),
    orl_lower_bound_status: str = Form('Unknown'),
    orl_physical_mode: str = Form('disabled'),
    output_mode: str = Form('fastreporter'),
    exporter_name: str = Form(''),
    unit: str = Form(''),
    route_name: str = Form(''),
    stv_total_core: str = Form(''),
    stv_used_core: str = Form(''),
) -> Response:
    import io
    import zipfile

    payload: list[tuple[str, bytes]] = []
    for upload in files:
        fn = (upload.filename or '').lower()
        if fn.endswith('.zip'):
            zip_bytes = await upload.read()
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                for zinfo in z.infolist():
                    if zinfo.is_dir():
                        continue
                    zname = zinfo.filename.lower()
                    if zname.endswith(('.sor', '.msor', '.trc')):
                        with z.open(zinfo) as zfile:
                            base_name = os.path.basename(zinfo.filename)
                            if base_name:
                                payload.append((base_name, zfile.read()))
        else:
            payload.append((upload.filename or 'upload.bin', await upload.read()))

    response = _build_export_response(
        payload,
        threshold_db=threshold_db,
        section_threshold_db=section_threshold_db,
        duration_threshold_s=duration_threshold_s,
        deviation_m=deviation_m,
        expected_route_km=expected_route_km,
        jumper_excluded_m=jumper_excluded_m,
        graph_reach_tolerance_km=graph_reach_tolerance_km,
        event_shortfall_tolerance_km=event_shortfall_tolerance_km,
        overlength_tolerance_km=overlength_tolerance_km,
        segment_start_km=segment_start_km,
        segment_end_km=segment_end_km,
        section_export_scope=section_export_scope,
        section_merge_tolerance_m=section_merge_tolerance_m,
        section_min_length_km=section_min_length_km,
        section_event_source=section_event_source,
        section_boundary_priority=section_boundary_priority,
        section_allow_split=section_allow_split,
        section_match_tolerance_m=section_match_tolerance_m,
        section_measurement_mode=section_measurement_mode,
        orl_pass_threshold_db=orl_pass_threshold_db,
        orl_source_mode=orl_source_mode,
        orl_missing_policy=orl_missing_policy,
        orl_allow_lower_bound=orl_allow_lower_bound,
        orl_lower_bound_status=orl_lower_bound_status,
        orl_physical_mode=orl_physical_mode,
        output_mode=output_mode,
        stv_total_core=stv_total_core,
        stv_used_core=stv_used_core,
    )
    _record_export_history(exporter_name, unit, route_name)
    return response


def _filename_from_export_response(response: Response) -> str:
    disposition = response.headers.get('content-disposition', '')
    marker = 'filename='
    if marker not in disposition:
        raise BlobStorageError('converter response is missing an output filename')
    raw_filename = disposition.split(marker, 1)[1].split(';', 1)[0].strip().strip('"')
    filename = os.path.basename(raw_filename)
    if not filename or filename != raw_filename or not filename.lower().endswith('.xlsx'):
        raise BlobStorageError('converter returned an invalid output filename')
    return filename


def _blob_http_exception(exc: BlobStorageError) -> HTTPException:
    if isinstance(exc, BlobStorageNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, BlobStorageSizeError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, BlobStorageConfigurationError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, BlobStorageOperationError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.post('/convert-from-blob')
async def convert_from_blob(
    upload_id: str = Form(...),
    input_manifest: str = Form(''),
    input_pathname: str = Form(''),
    threshold_db: float = Form(0.5),
    section_threshold_db: str = Form(''),
    duration_threshold_s: str = Form(''),
    deviation_m: float = Form(100.0),
    expected_route_km: str = Form(''),
    jumper_excluded_m: float = Form(0.0),
    graph_reach_tolerance_km: float = Form(0.030),
    event_shortfall_tolerance_km: float = Form(0.500),
    overlength_tolerance_km: float = Form(0.500),
    segment_start_km: str = Form(''),
    segment_end_km: str = Form(''),
    section_export_scope: str = Form('all'),
    section_merge_tolerance_m: float = Form(100.0),
    section_min_length_km: float = Form(0.0),
    section_event_source: str = Form('all'),
    section_boundary_priority: str = Form('event'),
    section_allow_split: str = Form('false'),
    section_match_tolerance_m: float = Form(100.0),
    section_measurement_mode: str = Form('fit'),
    orl_pass_threshold_db: float = Form(28.0),
    orl_source_mode: str = Form('auto'),
    orl_missing_policy: str = Form('reference'),
    orl_allow_lower_bound: str = Form('true'),
    orl_lower_bound_status: str = Form('Unknown'),
    orl_physical_mode: str = Form('disabled'),
    output_mode: str = Form('fastreporter'),
    exporter_name: str = Form(''),
    unit: str = Form(''),
    route_name: str = Form(''),
    stv_total_core: str = Form(''),
    stv_used_core: str = Form(''),
) -> JSONResponse:
    try:
        canonical_upload_id = str(UUID(str(upload_id)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail='upload_id must be a valid UUID',
        ) from exc

    if canonical_upload_id != upload_id:
        raise HTTPException(
            status_code=400,
            detail='upload_id must be a canonical UUID',
        )

    try:
        manifest_items: list[dict] = []
        if input_manifest.strip():
            try:
                decoded_manifest = json.loads(input_manifest)
            except json.JSONDecodeError as exc:
                raise BlobStorageError('input manifest is not valid JSON') from exc
            if not isinstance(decoded_manifest, list) or not decoded_manifest:
                raise BlobStorageError('input manifest must contain at least one file')

            extensions: set[str] = set()
            seen_paths: set[str] = set()
            total_size = 0
            for item in decoded_manifest:
                if not isinstance(item, dict):
                    raise BlobStorageError('input manifest item is invalid')
                original_name = item.get('original_name')
                pathname = item.get('pathname')
                size = item.get('size')
                if (
                    not isinstance(original_name, str)
                    or not original_name
                    or os.path.basename(original_name.replace('\\', '/'))
                    != original_name
                    or not isinstance(pathname, str)
                    or not isinstance(size, int)
                    or isinstance(size, bool)
                    or size <= 0
                ):
                    raise BlobStorageError('input manifest item is invalid')
                extension = os.path.splitext(original_name)[1].lower()
                if extension not in SUPPORTED_INPUT_EXTENSIONS:
                    raise BlobStorageError('input manifest extension is unsupported')
                if job_id_from_input_file_path(pathname) != canonical_upload_id:
                    raise BlobStorageError(
                        'upload_id does not match an input Blob pathname'
                    )
                if pathname in seen_paths:
                    raise BlobStorageError('input manifest contains a duplicate pathname')
                seen_paths.add(pathname)
                extensions.add(extension)
                total_size += size
                manifest_items.append(
                    {
                        'original_name': original_name,
                        'pathname': pathname,
                        'size': size,
                    }
                )

            if len(extensions) != 1:
                raise BlobStorageError(
                    'input manifest must contain exactly one OTDR file type'
                )
            if total_size > DEFAULT_MAX_DOWNLOAD_BYTES:
                raise BlobStorageSizeError(
                    'input manifest exceeds the configured total size limit'
                )
        elif input_pathname.strip():
            if job_id_from_input_path(input_pathname) != canonical_upload_id:
                raise BlobStorageError(
                    'upload_id does not match the input Blob pathname'
                )
        else:
            raise BlobStorageError('input manifest is required')

        with PrivateBlobStorage() as storage:
            def payloads() -> Iterable[tuple[str, bytes]]:
                if manifest_items:
                    for item in manifest_items:
                        yield (
                            item['original_name'],
                            storage.download_bytes(
                                item['pathname'],
                                max_bytes=item['size'],
                                expected_size=item['size'],
                            ),
                        )
                    return

                import zipfile

                zip_bytes = storage.download_bytes(input_pathname)
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
                    for zinfo in archive.infolist():
                        if zinfo.is_dir():
                            continue
                        extension = os.path.splitext(zinfo.filename)[1].lower()
                        if extension not in SUPPORTED_INPUT_EXTENSIONS:
                            continue
                        base_name = os.path.basename(zinfo.filename)
                        if base_name:
                            with archive.open(zinfo) as source:
                                yield base_name, source.read()

            export_response = _build_export_response(
                payloads(),
                threshold_db=threshold_db,
                section_threshold_db=section_threshold_db,
                duration_threshold_s=duration_threshold_s,
                deviation_m=deviation_m,
                expected_route_km=expected_route_km,
                jumper_excluded_m=jumper_excluded_m,
                graph_reach_tolerance_km=graph_reach_tolerance_km,
                event_shortfall_tolerance_km=event_shortfall_tolerance_km,
                overlength_tolerance_km=overlength_tolerance_km,
                segment_start_km=segment_start_km,
                segment_end_km=segment_end_km,
                section_export_scope=section_export_scope,
                section_merge_tolerance_m=section_merge_tolerance_m,
                section_min_length_km=section_min_length_km,
                section_event_source=section_event_source,
                section_boundary_priority=section_boundary_priority,
                section_allow_split=section_allow_split,
                section_match_tolerance_m=section_match_tolerance_m,
                section_measurement_mode=section_measurement_mode,
                orl_pass_threshold_db=orl_pass_threshold_db,
                orl_source_mode=orl_source_mode,
                orl_missing_policy=orl_missing_policy,
                orl_allow_lower_bound=orl_allow_lower_bound,
                orl_lower_bound_status=orl_lower_bound_status,
                orl_physical_mode=orl_physical_mode,
                output_mode=output_mode,
                stv_total_core=stv_total_core,
                stv_used_core=stv_used_core,
            )

            filename = _filename_from_export_response(export_response)
            output_bytes = bytes(export_response.body)
            output_pathname = build_output_path(canonical_upload_id, filename)
            stored = storage.upload_bytes(
                output_pathname,
                output_bytes,
                content_type=XLSX_CONTENT_TYPE,
                overwrite=False,
            )
            verified = storage.metadata(stored.pathname)
            if verified.size != len(output_bytes):
                raise BlobStorageSizeError(
                    'stored report size does not match the generated output'
                )
            _record_export_history(exporter_name, unit, route_name)

            for item in manifest_items:
                try:
                    storage.delete(item['pathname'])
                except BlobStorageError as cleanup_error:
                    print(
                        f"Warning: Could not delete input Blob "
                        f"{item['pathname']}: {cleanup_error}"
                    )
    except BlobStorageError as exc:
        raise _blob_http_exception(exc) from exc

    return JSONResponse(
        {
            "upload_id": canonical_upload_id,
            "status": "succeeded",
            "filename": filename,
            "output_pathname": stored.pathname,
            "content_type": stored.content_type,
            "size": stored.size,
        }
    )

@app.get('/api/history')
async def get_history() -> JSONResponse:
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, exporter_name, unit, route_name, export_time FROM export_history ORDER BY id DESC LIMIT 100')
        rows = c.fetchall()
        conn.close()
        history = [
            {
                "id": r[0],
                "exporter_name": r[1],
                "unit": r[2],
                "route_name": r[3],
                "export_time": r[4]
            }
            for r in rows
        ]
        return JSONResponse(content={"status": "success", "data": history})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})


@app.get('/api/notifications')
async def get_notifications() -> JSONResponse:
    try:
        import sqlite3
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, exporter_name, unit, route_name, export_time FROM export_history ORDER BY id DESC LIMIT 50')
        rows = c.fetchall()
        
        notifications = []
        for r in rows:
            nid, name, unit, route, time_str = r
            month_str = time_str[:7] if (time_str and len(time_str) >= 7) else ""
            month_name = time_str[5:7] if (time_str and len(time_str) >= 7) else ""
            
            if route and month_str:
                c.execute('SELECT COUNT(*) FROM export_history WHERE route_name = ? AND export_time LIKE ?', (route, f"{month_str}%"))
                count = c.fetchone()[0]
            else:
                count = 1
            
            msg = f"Nhân sự {name} ({unit}) vừa xuất tuyến {route}. Tuyến này đã được xuất {count} lần trong tháng {month_name}."
            notifications.append({
                "id": nid,
                "message": msg,
                "export_time": time_str,
                "exporter_name": name,
                "route_name": route,
                "count": count
            })
            
        conn.close()
        return JSONResponse(content={"status": "success", "data": notifications})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})



from .app_current import OTDRParserFactory

@app.post("/api/upload-otdr")
async def upload_otdr(files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        file_bytes = await file.read()
        parser = OTDRParserFactory.get_parser(file.filename)
        parsed_traces = parser.parse_to_standard_format(file_bytes)
        results.append({
            "status": "success", 
            "filename": file.filename, 
            "total_traces": len(parsed_traces), 
            "traces": parsed_traces
        })
    return JSONResponse(content={"results": results})

if os.path.exists("react_build/static"):
    app.mount("/static", StaticFiles(directory="react_build/static"), name="react_static")

@app.get("/graph")
async def serve_graph():
    from fastapi.responses import HTMLResponse
    if os.path.exists("react_build/index.html"):
        with open("react_build/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="React App chưa được build hoặc không tìm thấy.", status_code=404)
