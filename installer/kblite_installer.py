#!/usr/bin/env python3
"""
KBLite セットアップ
--uninstall 引数なし: インストールウィザード
--uninstall 引数あり: アンインストールウィザード
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import tkinter.scrolledtext as st
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# ============================================================
# 定数
# ============================================================
APP_NAME = "KBLite"
APP_VERSION = "1.0.0"
DEFAULT_INSTALL_PATH = r"C:\KBLite"

CLAUDE_CODE_INSTALL_URL = "https://docs.anthropic.com/ja/docs/claude-code"
CLAUDE_SIGNUP_URL = "https://claude.ai/upgrade"

REGISTRY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "KBLite"
REGISTRY_UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\KBLite"

DISCLAIMER_TEXT = """【免責事項】

このアプリケーション（KBLite）を利用したことによる
いかなる損害・不利益・データの損失・システムの障害等が発生しても、
開発者は一切の責任を負いません。

本アプリケーションは現状のまま（AS-IS）で提供されます。
動作保証・サポートの提供も行いません。

インストールを続行することにより、
上記の免責事項を読み、内容を理解した上で同意したものとみなします。

--------------------------------------------------------------

本アプリケーションを利用するには以下が必要です：
  ・Python 3.10 以上
  ・Claude Code（Pro Plan 以上）
  ・インターネット接続

インストール前に上記の要件を満たしているか確認してください。
"""

# ============================================================
# インストーラー本体
# ============================================================
class KBLiteInstaller(tk.Tk):

    # ----------------------------------------------------------
    # 初期化
    # ----------------------------------------------------------
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} セットアップ")
        self.geometry("700x540")
        self.resizable(False, False)
        self.configure(bg="#f5f5f5")

        # ウィンドウ中央表示
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 700) // 2
        y = (self.winfo_screenheight() - 540) // 2
        self.geometry(f"700x540+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 状態変数
        self.current_page = 0
        self.install_path = tk.StringVar(value=DEFAULT_INSTALL_PATH)
        self.agreed = tk.BooleanVar(value=False)
        self.create_shortcut = tk.BooleanVar(value=True)
        self.create_startup = tk.BooleanVar(value=False)
        self.launch_now = tk.BooleanVar(value=True)
        self.claude_status = {"installed": False, "authenticated": False}
        self._install_done = False

        self._build_ui()
        self._show_page(0)

    # ----------------------------------------------------------
    # UI 構築
    # ----------------------------------------------------------
    def _build_ui(self):
        # ヘッダー
        hdr = tk.Frame(self, bg="#1a252f", height=72)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text=f"  {APP_NAME}  セットアップ ウィザード",
                 font=("Meiryo UI", 17, "bold"), fg="white", bg="#1a252f",
                 anchor="w").pack(side="left", fill="both", expand=True, padx=18)
        tk.Label(hdr, text=f"v{APP_VERSION}",
                 font=("Meiryo UI", 9), fg="#aab", bg="#1a252f").pack(side="right", padx=18)

        # ステップインジケーター
        step_bar = tk.Frame(self, bg="#e0e0e0", height=32)
        step_bar.pack(fill="x")
        step_bar.pack_propagate(False)
        self._step_labels = []
        steps = ["免責事項", "Claude Code", "インストール先", "インストール中", "完了"]
        for i, s in enumerate(steps):
            lbl = tk.Label(step_bar, text=f"  {i+1}. {s}  ",
                           font=("Meiryo UI", 8), bg="#e0e0e0", fg="#999")
            lbl.pack(side="left", pady=7)
            self._step_labels.append(lbl)

        # コンテンツエリア
        self._content = tk.Frame(self, bg="#f5f5f5")
        self._content.pack(fill="both", expand=True, padx=30, pady=18)

        # ナビゲーションバー
        nav = tk.Frame(self, bg="#e8e8e8", height=52)
        nav.pack(fill="x")
        nav.pack_propagate(False)
        nav.configure(relief="groove", bd=1)

        self._btn_cancel = tk.Button(nav, text="キャンセル", width=11,
                                     command=self._on_close, font=("Meiryo UI", 9))
        self._btn_cancel.pack(side="left", padx=15, pady=10)

        self._btn_next = tk.Button(nav, text="次へ(N) >", width=12,
                                   command=self._on_next, font=("Meiryo UI", 9),
                                   bg="#1a252f", fg="white", activebackground="#2c3e50",
                                   activeforeground="white")
        self._btn_next.pack(side="right", padx=8, pady=10)

        self._btn_back = tk.Button(nav, text="< 戻る(B)", width=12,
                                   command=self._on_back, font=("Meiryo UI", 9),
                                   state="disabled")
        self._btn_back.pack(side="right", padx=2, pady=10)

        # ページ生成
        self._pages = [
            self._page_disclaimer(),
            self._page_claude(),
            self._page_location(),
            self._page_installing(),
            self._page_complete(),
        ]

    # ----------------------------------------------------------
    # ページ: 1 免責事項
    # ----------------------------------------------------------
    def _page_disclaimer(self) -> tk.Frame:
        f = tk.Frame(self._content, bg="#f5f5f5")

        tk.Label(f, text="免責事項のご確認", font=("Meiryo UI", 13, "bold"),
                 bg="#f5f5f5", anchor="w").pack(fill="x", pady=(0, 10))
        tk.Label(f, text="インストールを続行する前に、以下の免責事項をお読みください。",
                 font=("Meiryo UI", 9), bg="#f5f5f5", anchor="w", fg="#555").pack(fill="x")

        txt_frame = tk.Frame(f, bd=1, relief="sunken")
        txt_frame.pack(fill="both", expand=True, pady=(10, 0))
        self._txt_disclaimer = st.ScrolledText(
            txt_frame, wrap="word", font=("Meiryo UI", 10),
            height=11, bg="white", state="normal", padx=12, pady=10)
        self._txt_disclaimer.pack(fill="both", expand=True)
        self._txt_disclaimer.insert("end", DISCLAIMER_TEXT)
        self._txt_disclaimer.configure(state="disabled")

        agree_f = tk.Frame(f, bg="#f5f5f5")
        agree_f.pack(fill="x", pady=(12, 0))
        self._chk_agree = tk.Checkbutton(
            agree_f, text="上記の免責事項を読み、内容に同意します",
            variable=self.agreed, command=self._refresh_nav,
            font=("Meiryo UI", 10), bg="#f5f5f5")
        self._chk_agree.pack(side="left")

        return f

    # ----------------------------------------------------------
    # ページ: 2 Claude Code セットアップ
    # ----------------------------------------------------------
    def _page_claude(self) -> tk.Frame:
        f = tk.Frame(self._content, bg="#f5f5f5")

        tk.Label(f, text="Claude Code のセットアップ", font=("Meiryo UI", 13, "bold"),
                 bg="#f5f5f5", anchor="w").pack(fill="x", pady=(0, 6))
        tk.Label(f, text="KBLite の動作には Claude Code (Pro Plan 以上) が必要です。",
                 font=("Meiryo UI", 9), bg="#f5f5f5", anchor="w", fg="#555").pack(fill="x")

        # --- インストール状態 ---
        box1 = tk.LabelFrame(f, text=" Claude Code インストール状態 ",
                              font=("Meiryo UI", 9), bg="#f5f5f5", padx=14, pady=10)
        box1.pack(fill="x", pady=(14, 6))

        self._lbl_install_status = tk.Label(box1, text="確認中...",
                                             font=("Meiryo UI", 10), bg="#f5f5f5",
                                             anchor="w", fg="#888")
        self._lbl_install_status.pack(fill="x")

        r1 = tk.Frame(box1, bg="#f5f5f5")
        r1.pack(fill="x", pady=(6, 0))
        self._btn_get_claude = tk.Button(
            r1, text="Claude Code をダウンロードする",
            command=lambda: webbrowser.open(CLAUDE_CODE_INSTALL_URL),
            font=("Meiryo UI", 9), state="disabled")
        self._btn_get_claude.pack(side="left")
        tk.Button(r1, text="再確認", font=("Meiryo UI", 9),
                  command=self._check_claude_installed).pack(side="left", padx=(8, 0))

        # --- 認証状態 ---
        box2 = tk.LabelFrame(f, text=" Claude Code 認証状態 ",
                              font=("Meiryo UI", 9), bg="#f5f5f5", padx=14, pady=10)
        box2.pack(fill="x", pady=(0, 6))

        self._lbl_auth_status = tk.Label(box2, text="---",
                                          font=("Meiryo UI", 10), bg="#f5f5f5",
                                          anchor="w", fg="#888")
        self._lbl_auth_status.pack(fill="x")

        r2 = tk.Frame(box2, bg="#f5f5f5")
        r2.pack(fill="x", pady=(6, 0))
        self._btn_auth = tk.Button(r2, text="ブラウザで認証する",
                                    command=self._start_auth,
                                    font=("Meiryo UI", 9), state="disabled")
        self._btn_auth.pack(side="left")
        tk.Button(r2, text="Claudeに加入する",
                  command=lambda: webbrowser.open(CLAUDE_SIGNUP_URL),
                  font=("Meiryo UI", 9)).pack(side="left", padx=(8, 0))
        tk.Button(r2, text="再確認", font=("Meiryo UI", 9),
                  command=self._check_claude_auth).pack(side="left", padx=(8, 0))

        tk.Label(f, text="※ 認証完了後に「再確認」ボタンを押してください",
                 font=("Meiryo UI", 8), bg="#f5f5f5", fg="#e67e22",
                 anchor="w").pack(fill="x")

        return f

    # ----------------------------------------------------------
    # ページ: 3 インストール先
    # ----------------------------------------------------------
    def _page_location(self) -> tk.Frame:
        f = tk.Frame(self._content, bg="#f5f5f5")

        tk.Label(f, text="インストール先の選択", font=("Meiryo UI", 13, "bold"),
                 bg="#f5f5f5", anchor="w").pack(fill="x", pady=(0, 6))
        tk.Label(f, text="KBLite をインストールするフォルダーを指定してください。",
                 font=("Meiryo UI", 9), bg="#f5f5f5", anchor="w", fg="#555").pack(fill="x")

        path_f = tk.Frame(f, bg="#f5f5f5")
        path_f.pack(fill="x", pady=(18, 0))
        self._entry_path = tk.Entry(path_f, textvariable=self.install_path,
                                    font=("Meiryo UI", 10), width=52)
        self._entry_path.pack(side="left", fill="x", expand=True)
        tk.Button(path_f, text="参照...", font=("Meiryo UI", 9),
                  command=self._browse_path).pack(side="left", padx=(8, 0))

        info_box = tk.LabelFrame(f, text=" インストール情報 ",
                                  font=("Meiryo UI", 9), bg="#f5f5f5", padx=14, pady=10)
        info_box.pack(fill="x", pady=(16, 0))
        self._lbl_disk_info = tk.Label(info_box, text="",
                                        font=("Meiryo UI", 10), bg="#f5f5f5",
                                        anchor="w", justify="left")
        self._lbl_disk_info.pack(fill="x")

        self.install_path.trace_add("write", lambda *_: self._update_disk_info())
        self._update_disk_info()

        opt_f = tk.Frame(f, bg="#f5f5f5")
        opt_f.pack(fill="x", pady=(18, 0))
        tk.Checkbutton(opt_f, text="デスクトップにショートカットを作成する",
                       variable=self.create_shortcut,
                       font=("Meiryo UI", 10), bg="#f5f5f5").pack(anchor="w")
        tk.Checkbutton(opt_f, text="Windows 起動時に自動的に KBLite を起動する",
                       variable=self.create_startup,
                       font=("Meiryo UI", 10), bg="#f5f5f5").pack(anchor="w", pady=(6, 0))

        return f

    # ----------------------------------------------------------
    # ページ: 4 インストール中
    # ----------------------------------------------------------
    def _page_installing(self) -> tk.Frame:
        f = tk.Frame(self._content, bg="#f5f5f5")

        tk.Label(f, text="インストール中", font=("Meiryo UI", 13, "bold"),
                 bg="#f5f5f5", anchor="w").pack(fill="x", pady=(0, 12))

        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ttk.Progressbar(f, variable=self._progress_var,
                                              maximum=100, length=620)
        self._progress_bar.pack(fill="x")

        self._lbl_step = tk.Label(f, text="",
                                   font=("Meiryo UI", 9), bg="#f5f5f5",
                                   anchor="w", fg="#555")
        self._lbl_step.pack(fill="x", pady=(4, 0))

        log_f = tk.Frame(f, bd=1, relief="sunken")
        log_f.pack(fill="both", expand=True, pady=(10, 0))
        self._log_box = st.ScrolledText(
            log_f, wrap="word", font=("Courier New", 8),
            height=12, bg="#1e1e1e", fg="#cccccc",
            state="disabled", padx=10, pady=8)
        self._log_box.pack(fill="both", expand=True)

        return f

    # ----------------------------------------------------------
    # ページ: 5 完了
    # ----------------------------------------------------------
    def _page_complete(self) -> tk.Frame:
        f = tk.Frame(self._content, bg="#f5f5f5")

        center = tk.Frame(f, bg="#f5f5f5")
        center.pack(expand=True, fill="both")

        tk.Label(center, text="✓", font=("Arial", 52), fg="#27ae60",
                 bg="#f5f5f5").pack(pady=(30, 8))
        tk.Label(center, text="インストール完了！",
                 font=("Meiryo UI", 20, "bold"), bg="#f5f5f5").pack()
        tk.Label(center, text=f"{APP_NAME} のインストールが正常に完了しました。",
                 font=("Meiryo UI", 11), bg="#f5f5f5", fg="#555").pack(pady=(8, 0))
        self._lbl_install_result = tk.Label(center, text="",
                                             font=("Meiryo UI", 9), bg="#f5f5f5", fg="#888")
        self._lbl_install_result.pack(pady=(4, 22))

        tk.Checkbutton(center, text="今すぐ KBLite をブラウザで開く",
                       variable=self.launch_now,
                       font=("Meiryo UI", 11), bg="#f5f5f5").pack()

        return f

    # ----------------------------------------------------------
    # ページ切替・ナビゲーション
    # ----------------------------------------------------------
    def _show_page(self, index: int):
        for page in self._pages:
            page.pack_forget()
        self._pages[index].pack(fill="both", expand=True)
        self.current_page = index

        # ステップ色更新
        for i, lbl in enumerate(self._step_labels):
            if i < index:
                lbl.configure(fg="#27ae60", font=("Meiryo UI", 8, "bold"))
            elif i == index:
                lbl.configure(fg="#1a252f", font=("Meiryo UI", 8, "bold"))
            else:
                lbl.configure(fg="#aaa", font=("Meiryo UI", 8))

        # ページ固有の初期化
        if index == 1:
            self._check_claude_installed()
        elif index == 4:
            self._lbl_install_result.configure(
                text=f"インストール先: {self.install_path.get()}")
            # stateを明示的に"normal"に戻す（page 3で"disabled"になったまま引き継がれるため）
            self._btn_next.configure(text="完了(F)", command=self._on_finish, state="normal")
            self._btn_back.configure(state="disabled")
            self._btn_cancel.configure(state="disabled")

        self._btn_back.configure(state="normal" if 0 < index < 3 else "disabled")
        self._refresh_nav()

    def _refresh_nav(self):
        if self.current_page == 0:
            state = "normal" if self.agreed.get() else "disabled"
        elif self.current_page == 1:
            ok = self.claude_status["installed"] and self.claude_status["authenticated"]
            state = "normal" if ok else "disabled"
        elif self.current_page == 3:
            state = "disabled"
        else:
            state = "normal"
        if self.current_page != 4:
            self._btn_next.configure(state=state, text="次へ(N) >", command=self._on_next)

    def _on_next(self):
        if self.current_page == 2:          # インストール開始
            self._show_page(3)
            threading.Thread(target=self._run_install, daemon=True).start()
        else:
            self._show_page(self.current_page + 1)

    def _on_back(self):
        self._show_page(self.current_page - 1)

    def _on_close(self):
        if self._install_done:
            self.destroy()
            return
        if messagebox.askyesno("キャンセル確認", "セットアップをキャンセルしますか？"):
            self.destroy()

    def _on_finish(self):
        if self.launch_now.get():
            self._launch_kblite()
        self.destroy()

    # ----------------------------------------------------------
    # Claude Code チェック
    # ----------------------------------------------------------
    def _check_claude_installed(self):
        self._lbl_install_status.configure(text="確認中...", fg="#888")
        threading.Thread(target=self._do_check_installed, daemon=True).start()

    def _do_check_installed(self):
        installed = False
        version_str = ""
        # Windows では claude.cmd / claude.ps1 が PATH 経由で見つかるよう
        # shell=True で実行する。直接呼び出しだと npm グローバル bin が
        # 見つからないケースがある。
        for cmd in (["claude", "--version"], ["claude.cmd", "--version"]):
            try:
                r = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    shell=True
                )
                if r.returncode == 0:
                    installed = True
                    version_str = r.stdout.strip() or r.stderr.strip()
                    break
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue

        self.claude_status["installed"] = installed

        if installed:
            ver = f"（{version_str}）" if version_str else ""
            self.after(0, lambda: self._lbl_install_status.configure(
                text=f"✓ Claude Code がインストールされています {ver}", fg="#27ae60"))
            self.after(0, lambda: self._btn_get_claude.configure(state="disabled"))
            self.after(0, self._check_claude_auth)
        else:
            self.after(0, lambda: self._lbl_install_status.configure(
                text="✗ Claude Code が見つかりません", fg="#e74c3c"))
            self.after(0, lambda: self._btn_get_claude.configure(state="normal"))
            self.after(0, lambda: self._lbl_auth_status.configure(
                text="Claude Code をインストール後に認証してください", fg="#aaa"))
            self.after(0, self._refresh_nav)

    def _check_claude_auth(self):
        self._lbl_auth_status.configure(text="確認中...", fg="#888")
        threading.Thread(target=self._do_check_auth, daemon=True).start()

    def _do_check_auth(self):
        authenticated = False
        try:
            # `claude auth status` で認証状態を確認（shell=True でPATH解決）
            r = subprocess.run(
                ["claude", "auth", "status"],
                capture_output=True, text=True, timeout=12,
                creationflags=subprocess.CREATE_NO_WINDOW,
                shell=True
            )
            output = (r.stdout + r.stderr).lower()
            if r.returncode == 0 and ("logged in" in output or "authenticated" in output
                                       or "subscription" in output):
                authenticated = True
            elif "not logged in" in output or "not authenticated" in output:
                authenticated = False
            else:
                # フォールバック: ~/.claude/.credentials.json の存在確認
                cred_candidates = [
                    Path.home() / ".claude" / ".credentials.json",
                    Path.home() / ".claude" / "credentials.json",
                ]
                authenticated = any(p.exists() for p in cred_candidates)
        except Exception:
            # フォールバック確認
            try:
                cred_candidates = [
                    Path.home() / ".claude" / ".credentials.json",
                    Path.home() / ".claude" / "credentials.json",
                ]
                authenticated = any(p.exists() for p in cred_candidates)
            except Exception:
                authenticated = False

        self.claude_status["authenticated"] = authenticated

        if authenticated:
            self.after(0, lambda: self._lbl_auth_status.configure(
                text="✓ Claude Code の認証が完了しています", fg="#27ae60"))
            self.after(0, lambda: self._btn_auth.configure(state="disabled"))
        else:
            self.after(0, lambda: self._lbl_auth_status.configure(
                text="✗ 認証されていません。ブラウザで認証してください。", fg="#e74c3c"))
            if self.claude_status["installed"]:
                self.after(0, lambda: self._btn_auth.configure(state="normal"))

        self.after(0, self._refresh_nav)

    def _start_auth(self):
        """ブラウザ経由で claude auth login を起動"""
        self._btn_auth.configure(state="disabled", text="ブラウザ起動中...")
        self._lbl_auth_status.configure(
            text="ブラウザで認証を完了してください。完了後「再確認」を押してください。",
            fg="#e67e22")
        threading.Thread(target=self._do_start_auth, daemon=True).start()

    def _do_start_auth(self):
        try:
            subprocess.Popen(
                ["claude", "auth", "login"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                shell=True
            )
        except Exception as e:
            self.after(0, lambda: messagebox.showerror(
                "エラー", f"認証の開始に失敗しました:\n{e}"))
        self.after(0, lambda: self._btn_auth.configure(
            state="normal", text="ブラウザで認証する"))

    # ----------------------------------------------------------
    # インストール先ページ
    # ----------------------------------------------------------
    def _browse_path(self):
        path = filedialog.askdirectory(title="インストール先フォルダーを選択")
        if path:
            self.install_path.set(os.path.normpath(path))

    def _update_disk_info(self):
        path = self.install_path.get()
        try:
            drive = os.path.splitdrive(path)[0] + "\\"
            if os.path.exists(drive):
                total, used, free = shutil.disk_usage(drive)
                free_gb = free / (1024 ** 3)
                self._lbl_disk_info.configure(
                    text=f"インストール先: {path}\n"
                         f"ドライブ空き容量: {free_gb:.1f} GB")
            else:
                self._lbl_disk_info.configure(text=f"インストール先: {path}")
        except Exception:
            self._lbl_disk_info.configure(text=f"インストール先: {path}")

    # ----------------------------------------------------------
    # インストール処理
    # ----------------------------------------------------------
    def _log(self, msg: str):
        self.after(0, lambda m=msg: self._append_log(m))

    def _append_log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _set_progress(self, value: float, label: str = ""):
        self.after(0, lambda: self._progress_var.set(value))
        if label:
            self.after(0, lambda: self._lbl_step.configure(text=label))

    def _run_install(self):
        try:
            install_path = Path(self.install_path.get())
            source_path = self._resolve_source_path()

            # ---- Step 1: ディレクトリ作成 ----
            self._set_progress(5, "インストール先フォルダーを作成しています...")
            self._log(f"[1/7] フォルダー作成: {install_path}")
            install_path.mkdir(parents=True, exist_ok=True)

            # ---- Step 2: ファイルコピー ----
            self._set_progress(15, "KBLite ファイルをコピーしています...")
            self._log("[2/7] ファイルをコピーしています...")

            items = [
                "app.py", "app-config.json", "prompt.py",
                "sqlite_store.py", "deps.py", "statusline.py",
                "requirements.txt", "index.html",
                "routes", "stores", "static", "commands",
                "models", "services", "templates",
            ]
            # オプションファイル（存在する場合のみコピー）
            optional = ["mcp_tasks.py"]

            for item in items + optional:
                src = source_path / item
                dst = install_path / item
                if not src.exists():
                    if item not in optional:
                        self._log(f"  スキップ（存在しない）: {item}")
                    continue
                try:
                    if src.is_dir():
                        if dst.exists():
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                        self._log(f"  コピー: {item}/")
                    else:
                        shutil.copy2(src, dst)
                        self._log(f"  コピー: {item}")
                except Exception as e:
                    self._log(f"  警告: {item} のコピー失敗 - {e}")

            # ---- Step 3: データフォルダー ----
            self._set_progress(40, "データフォルダーを作成しています...")
            self._log("[3/7] データフォルダー作成...")
            (install_path / "data" / "sqlite").mkdir(parents=True, exist_ok=True)
            self._log("  data/sqlite/ 作成完了")

            # ---- Step 4: Python パッケージ ----
            self._set_progress(50, "Python パッケージをインストールしています...")
            self._log("[4/7] Python パッケージインストール...")
            req_file = install_path / "requirements.txt"
            if req_file.exists():
                python_exe = self._find_python()
                self._log(f"  Python: {python_exe}")
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "-r", str(req_file),
                     "--quiet"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    self._log("  インストール完了")
                else:
                    self._log(f"  警告（続行します）: {result.stderr[:300]}")

            # ---- Step 5: 起動スクリプト ----
            self._set_progress(65, "起動スクリプトを作成しています...")
            self._log("[5/7] 起動スクリプト作成...")
            python_exe = self._find_python()
            self._create_startup_bat(install_path, python_exe)
            self._log("  start_kblite.bat / start_kblite_silent.bat / start_kblite.vbs 作成完了")

            # ---- Step 6: アンインストーラーをコピー + レジストリ登録 ----
            self._set_progress(75, "アンインストーラーを登録しています...")
            self._log("[6/7] アンインストーラー登録...")
            self._install_uninstaller(install_path)

            # ---- Step 7: ショートカット / スタートアップ ----
            self._set_progress(88, "ショートカットを作成しています...")
            self._log("[7/7] ショートカット処理...")
            if self.create_shortcut.get():
                self._create_desktop_shortcut(install_path)
            if self.create_startup.get():
                self._add_to_startup(install_path)

            # ---- 完了 ----
            self._set_progress(100, "インストール完了")
            self._log("")
            self._log("=" * 50)
            self._log("  KBLite のインストールが完了しました")
            self._log(f"  場所: {install_path}")
            self._log("=" * 50)

            self._install_done = True
            self.after(1200, lambda: self._show_page(4))

        except Exception as e:
            import traceback
            self._log(f"\nエラーが発生しました:\n{traceback.format_exc()}")
            self.after(0, lambda: messagebox.showerror(
                "インストールエラー",
                "インストール中にエラーが発生しました。\n\nログを確認してください。"))
            self.after(0, lambda: self._btn_back.configure(state="normal"))
            self.after(0, lambda: self._btn_cancel.configure(state="normal"))

    def _install_uninstaller(self, install_path: Path):
        """自分自身（exe）をインストール先にコピーしてレジストリに登録する"""
        # exe のコピー（PyInstaller でビルドされた場合のみ）
        if getattr(sys, "frozen", False):
            src_exe = Path(sys.executable)
            dst_exe = install_path / src_exe.name
            try:
                shutil.copy2(src_exe, dst_exe)
                self._log(f"  セットアップexeをコピー: {dst_exe.name}")
            except Exception as e:
                self._log(f"  exeコピー失敗（続行）: {e}")
                dst_exe = src_exe
        else:
            # 開発時は sys.executable（python.exe）のパスを使用
            dst_exe = Path(sys.executable)

        # レジストリ登録（プログラムの追加と削除）
        try:
            import winreg
            key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_UNINSTALL_KEY,
                0, winreg.KEY_SET_VALUE
            )
            uninstall_cmd = f'"{dst_exe}" --uninstall'
            winreg.SetValueEx(key, "DisplayName",       0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion",    0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher",         0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "InstallLocation",   0, winreg.REG_SZ, str(install_path))
            winreg.SetValueEx(key, "UninstallString",   0, winreg.REG_SZ, uninstall_cmd)
            winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, uninstall_cmd)
            icon_path = str(install_path / "kblite.ico")
            winreg.SetValueEx(key, "DisplayIcon",       0, winreg.REG_SZ, icon_path)
            winreg.SetValueEx(key, "NoModify",          0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair",          0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            self._log("  プログラムの追加と削除に登録完了")
        except Exception as e:
            self._log(f"  レジストリ登録失敗（続行）: {e}")

    def _resolve_source_path(self) -> Path:
        """KBLite ソースファイルのパスを解決する"""
        if getattr(sys, "frozen", False):
            # PyInstaller --onefile モードでは _MEIPASS に展開される
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                src = Path(meipass) / "source"
                if src.exists():
                    return src
                return Path(meipass)
            # onedir モードの場合は exe 隣の source/ を参照
            base = Path(sys.executable).parent
            src = base / "source"
            if src.exists():
                return src
            return base
        else:
            # 開発時: installer/ の親ディレクトリ = kblite/ プロジェクトルート
            return Path(__file__).parent.parent

    def _find_python(self) -> str:
        """現在の Python 実行ファイルのパスを返す"""
        if getattr(sys, "frozen", False):
            # PyInstaller の場合は sys.executable はインストーラー自身なので
            # where コマンドでシステムの python のフルパスを取得する
            for candidate in ["python", "python3", "py"]:
                try:
                    r = subprocess.run(
                        ["where", candidate],
                        capture_output=True, text=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        first_path = r.stdout.strip().splitlines()[0].strip()
                        if first_path:
                            return first_path
                except Exception:
                    continue
            return "python"
        else:
            return sys.executable

    def _create_startup_bat(self, install_path: Path, python_exe: str):
        """起動スクリプト（bat×2 + vbs）を生成"""
        # start_kblite.bat: 手動起動・デバッグ用（コンソールウィンドウあり）
        bat = (
            "@echo off\n"
            "chcp 65001 >nul\n"
            f'cd /d "{install_path}"\n'
            f'"{python_exe}" -m uvicorn app:app --host 127.0.0.1 --port 8080\n'
        )
        (install_path / "start_kblite.bat").write_text(bat, encoding="utf-8")

        # start_kblite_silent.bat: VBSから呼ばれるサイレント起動用
        silent_bat = (
            "@echo off\n"
            "chcp 65001 >nul\n"
            f'cd /d "{install_path}"\n'
            f'if not exist "{install_path}\\logs" mkdir "{install_path}\\logs"\n'
            f'"{python_exe}" -m uvicorn app:app --host 127.0.0.1 --port 8080 '
            f'>> "{install_path}\\logs\\uvicorn.log" 2>&1\n'
        )
        (install_path / "start_kblite_silent.bat").write_text(
            silent_bat, encoding="utf-8"
        )

        # start_kblite.vbs: chr(34)でクォート — shell.Runの三重引用符問題を回避
        silent_bat_path = str(install_path / "start_kblite_silent.bat")
        vbs_lines = [
            'Set shell = CreateObject("WScript.Shell")',
            "q = chr(34)",
            f'shell.Run q & "{silent_bat_path}" & q, 0, False',
            "WScript.Sleep 3000",
            'shell.Run "http://localhost:8080", 1, False',
        ]
        vbs = "\r\n".join(vbs_lines) + "\r\n"
        (install_path / "start_kblite.vbs").write_text(vbs, encoding="utf-8")

    def _create_desktop_shortcut(self, install_path: Path):
        try:
            desktop = Path.home() / "Desktop"
            if not desktop.exists():
                # OneDrive 等の場合
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r"Software\Microsoft\Windows\CurrentVersion"
                                     r"\Explorer\Shell Folders")
                desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])

            shortcut = desktop / "KBLite.lnk"
            startup_vbs = install_path / "start_kblite.vbs"

            vbs = (
                'Set ws = WScript.CreateObject("WScript.Shell")\n'
                "q = chr(34)\n"
                f'Set lnk = ws.CreateShortcut("{shortcut}")\n'
                'lnk.TargetPath = "wscript.exe"\n'
                f'lnk.Arguments = q & "{startup_vbs}" & q\n'
                f'lnk.WorkingDirectory = "{install_path}"\n'
                'lnk.Description = "KBLite Knowledge Base Browser"\n'
                'lnk.Save\n'
            )
            with tempfile.NamedTemporaryFile(suffix=".vbs", delete=False,
                                             mode="w", encoding="utf-8") as f:
                vbs_path = f.name
                f.write(vbs)

            subprocess.run(["wscript", vbs_path],
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            os.unlink(vbs_path)
            self._log("  デスクトップショートカット作成完了")
        except Exception as e:
            self._log(f"  ショートカット作成失敗（続行）: {e}")

    def _add_to_startup(self, install_path: Path):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            vbs_path = str(install_path / "start_kblite.vbs")
            winreg.SetValueEx(key, "KBLite", 0, winreg.REG_SZ, f'wscript.exe "{vbs_path}"')
            winreg.CloseKey(key)
            self._log("  スタートアップ登録完了")
        except Exception as e:
            self._log(f"  スタートアップ登録失敗（続行）: {e}")

    def _copy_uninstaller(self, install_path: Path, source_path: Path) -> Path | None:
        """アンインストーラー EXE をインストールフォルダーにコピーする"""
        if getattr(sys, "frozen", False):
            # インストーラーEXEに同梱されている場合（_MEIPASS）を優先
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                uninstaller_src = Path(meipass) / "KBLite_Uninstall.exe"
            else:
                uninstaller_src = Path(sys.executable).parent / "KBLite_Uninstall.exe"
        else:
            uninstaller_src = Path(__file__).parent / "dist" / "KBLite_Uninstall.exe"

        if uninstaller_src.exists():
            dst = install_path / "KBLite_Uninstall.exe"
            shutil.copy2(str(uninstaller_src), str(dst))
            self._log("  KBLite_Uninstall.exe をコピーしました")
            return dst
        else:
            self._log("  アンインストーラーが見つかりません（スキップ）")
            self._log(f"  ※ {uninstaller_src}")
            return None

    def _register_uninstall_entry(self, install_path: Path, uninstaller_path: Path | None):
        """プログラムの追加と削除にアンインストール情報を登録する"""
        try:
            import winreg
            key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall\KBLite"
            )
            uninstall_str = (
                str(uninstaller_path)
                if uninstaller_path and uninstaller_path.exists()
                else str(install_path / "KBLite_Uninstall.exe")
            )
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "KBLite Project")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_path))
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninstall_str)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, uninstall_str)
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            self._log("  プログラムの追加と削除に登録しました")
        except Exception as e:
            self._log(f"  アプリ一覧登録失敗（続行）: {e}")

    def _launch_kblite(self):
        try:
            install_dir = Path(self.install_path.get())
            vbs_path = install_dir / "start_kblite.vbs"
            if vbs_path.exists():
                subprocess.Popen(["wscript", str(vbs_path)],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                bat_path = install_dir / "start_kblite.bat"
                if bat_path.exists():
                    subprocess.Popen(["cmd", "/c", str(bat_path)],
                                     creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            messagebox.showerror("起動エラー", f"KBLite の起動に失敗しました:\n{e}")


# ============================================================
# アンインストーラー本体
# ============================================================
class KBLiteUninstaller(tk.Tk):

    # ----------------------------------------------------------
    # 初期化
    # ----------------------------------------------------------
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} アンインストール")
        self.geometry("700x500")
        self.resizable(False, False)
        self.configure(bg="#f5f5f5")

        self.update_idletasks()
        x = (self.winfo_screenwidth() - 700) // 2
        y = (self.winfo_screenheight() - 500) // 2
        self.geometry(f"700x500+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.current_page = 0
        target = next(
            (a.split("=", 1)[1] for a in sys.argv if a.startswith("--target=")),
            None,
        )
        self.install_path = tk.StringVar(value=target or self._detect_install_path())
        self.keep_data = tk.BooleanVar(value=True)
        self._uninstall_done = False

        self._build_ui()
        self._show_page(0)

    # ----------------------------------------------------------
    # インストール先の自動検出
    # ----------------------------------------------------------
    def _detect_install_path(self) -> str:
        """レジストリまたはデフォルトパスからインストール先を検出する"""
        # 1. Add/Remove Programs の登録から取得（最も信頼できる）
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_UNINSTALL_KEY,
                0, winreg.KEY_READ
            )
            location, _ = winreg.QueryValueEx(key, "InstallLocation")
            winreg.CloseKey(key)
            if Path(location).exists():
                return location
        except Exception:
            pass

        # 2. スタートアップ登録から取得
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_RUN_KEY,
                0, winreg.KEY_READ
            )
            bat_path, _ = winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
            winreg.CloseKey(key)
            detected = str(Path(bat_path).parent)
            if Path(detected).exists():
                return detected
        except Exception:
            pass

        if Path(DEFAULT_INSTALL_PATH).exists():
            return DEFAULT_INSTALL_PATH
        return DEFAULT_INSTALL_PATH

    # ----------------------------------------------------------
    # UI 構築
    # ----------------------------------------------------------
    def _build_ui(self):
        # ヘッダー
        hdr = tk.Frame(self, bg="#7f1f1f", height=72)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text=f"  {APP_NAME}  アンインストール ウィザード",
                 font=("Meiryo UI", 17, "bold"), fg="white", bg="#7f1f1f",
                 anchor="w").pack(side="left", fill="both", expand=True, padx=18)
        tk.Label(hdr, text=f"v{APP_VERSION}",
                 font=("Meiryo UI", 9), fg="#daa", bg="#7f1f1f").pack(side="right", padx=18)

        # ステップインジケーター
        step_bar = tk.Frame(self, bg="#e0e0e0", height=32)
        step_bar.pack(fill="x")
        step_bar.pack_propagate(False)
        self._step_labels = []
        steps = ["確認", "アンインストール中", "完了"]
        for i, s in enumerate(steps):
            lbl = tk.Label(step_bar, text=f"  {i+1}. {s}  ",
                           font=("Meiryo UI", 8), bg="#e0e0e0", fg="#999")
            lbl.pack(side="left", pady=7)
            self._step_labels.append(lbl)

        # コンテンツエリア
        self._content = tk.Frame(self, bg="#f5f5f5")
        self._content.pack(fill="both", expand=True, padx=30, pady=18)

        # ナビゲーションバー
        nav = tk.Frame(self, bg="#e8e8e8", height=52)
        nav.pack(fill="x")
        nav.pack_propagate(False)
        nav.configure(relief="groove", bd=1)

        self._btn_cancel = tk.Button(nav, text="キャンセル", width=11,
                                     command=self._on_close, font=("Meiryo UI", 9))
        self._btn_cancel.pack(side="left", padx=15, pady=10)

        self._btn_next = tk.Button(nav, text="アンインストール(U)", width=18,
                                   command=self._on_next, font=("Meiryo UI", 9),
                                   bg="#7f1f1f", fg="white", activebackground="#a03030",
                                   activeforeground="white")
        self._btn_next.pack(side="right", padx=8, pady=10)

        # ページ生成
        self._pages = [
            self._page_confirm(),
            self._page_uninstalling(),
            self._page_complete(),
        ]

    # ----------------------------------------------------------
    # ページ: 1 確認
    # ----------------------------------------------------------
    def _page_confirm(self) -> tk.Frame:
        f = tk.Frame(self._content, bg="#f5f5f5")

        tk.Label(f, text="アンインストールの確認", font=("Meiryo UI", 13, "bold"),
                 bg="#f5f5f5", anchor="w").pack(fill="x", pady=(0, 6))
        tk.Label(f, text="以下の内容を確認の上、アンインストールを実行してください。",
                 font=("Meiryo UI", 9), bg="#f5f5f5", anchor="w", fg="#555").pack(fill="x")

        # インストール先パス
        path_box = tk.LabelFrame(f, text=" アンインストール対象フォルダー ",
                                  font=("Meiryo UI", 9), bg="#f5f5f5", padx=14, pady=10)
        path_box.pack(fill="x", pady=(14, 6))

        path_f = tk.Frame(path_box, bg="#f5f5f5")
        path_f.pack(fill="x")
        self._entry_path = tk.Entry(path_f, textvariable=self.install_path,
                                    font=("Meiryo UI", 10), width=52)
        self._entry_path.pack(side="left", fill="x", expand=True)
        tk.Button(path_f, text="参照...", font=("Meiryo UI", 9),
                  command=self._browse_path).pack(side="left", padx=(8, 0))

        # 削除対象リスト
        items_box = tk.LabelFrame(f, text=" 削除される項目 ",
                                   font=("Meiryo UI", 9), bg="#f5f5f5", padx=14, pady=10)
        items_box.pack(fill="x", pady=(0, 6))

        items_text = (
            "・ インストールフォルダー内の全ファイル\n"
            "・ デスクトップショートカット（KBLite.lnk）\n"
            "・ スタートアップ登録（レジストリ）\n"
            "・ プログラムの追加と削除への登録"
        )
        tk.Label(items_box, text=items_text,
                 font=("Meiryo UI", 9), bg="#f5f5f5", anchor="w",
                 justify="left", fg="#333").pack(fill="x")

        # データ保持オプション
        opt_f = tk.Frame(f, bg="#f5f5f5")
        opt_f.pack(fill="x", pady=(8, 0))
        tk.Checkbutton(opt_f, text="会話履歴データ（data/ フォルダー）を残す",
                       variable=self.keep_data,
                       font=("Meiryo UI", 10), bg="#f5f5f5").pack(anchor="w")
        tk.Label(opt_f,
                 text="  ※ チェックを外すと会話履歴が完全に削除されます（復元不可）",
                 font=("Meiryo UI", 8), bg="#f5f5f5", fg="#e67e22",
                 anchor="w").pack(fill="x")

        return f

    # ----------------------------------------------------------
    # ページ: 2 アンインストール中
    # ----------------------------------------------------------
    def _page_uninstalling(self) -> tk.Frame:
        f = tk.Frame(self._content, bg="#f5f5f5")

        tk.Label(f, text="アンインストール中", font=("Meiryo UI", 13, "bold"),
                 bg="#f5f5f5", anchor="w").pack(fill="x", pady=(0, 12))

        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ttk.Progressbar(f, variable=self._progress_var,
                                              maximum=100, length=620)
        self._progress_bar.pack(fill="x")

        self._lbl_step = tk.Label(f, text="",
                                   font=("Meiryo UI", 9), bg="#f5f5f5",
                                   anchor="w", fg="#555")
        self._lbl_step.pack(fill="x", pady=(4, 0))

        log_f = tk.Frame(f, bd=1, relief="sunken")
        log_f.pack(fill="both", expand=True, pady=(10, 0))
        self._log_box = st.ScrolledText(
            log_f, wrap="word", font=("Courier New", 8),
            height=12, bg="#1e1e1e", fg="#cccccc",
            state="disabled", padx=10, pady=8)
        self._log_box.pack(fill="both", expand=True)

        return f

    # ----------------------------------------------------------
    # ページ: 3 完了
    # ----------------------------------------------------------
    def _page_complete(self) -> tk.Frame:
        f = tk.Frame(self._content, bg="#f5f5f5")

        center = tk.Frame(f, bg="#f5f5f5")
        center.pack(expand=True, fill="both")

        tk.Label(center, text="✓", font=("Arial", 52), fg="#27ae60",
                 bg="#f5f5f5").pack(pady=(30, 8))
        tk.Label(center, text="アンインストール完了！",
                 font=("Meiryo UI", 20, "bold"), bg="#f5f5f5").pack()
        tk.Label(center, text=f"{APP_NAME} が正常にアンインストールされました。",
                 font=("Meiryo UI", 11), bg="#f5f5f5", fg="#555").pack(pady=(8, 0))
        self._lbl_result = tk.Label(center, text="",
                                     font=("Meiryo UI", 9), bg="#f5f5f5", fg="#888")
        self._lbl_result.pack(pady=(4, 0))

        return f

    # ----------------------------------------------------------
    # ページ切替・ナビゲーション
    # ----------------------------------------------------------
    def _show_page(self, index: int):
        for page in self._pages:
            page.pack_forget()
        self._pages[index].pack(fill="both", expand=True)
        self.current_page = index

        for i, lbl in enumerate(self._step_labels):
            if i < index:
                lbl.configure(fg="#27ae60", font=("Meiryo UI", 8, "bold"))
            elif i == index:
                lbl.configure(fg="#7f1f1f", font=("Meiryo UI", 8, "bold"))
            else:
                lbl.configure(fg="#aaa", font=("Meiryo UI", 8))

        if index == 2:
            result_parts = [f"削除先: {self.install_path.get()}"]
            if self.keep_data.get():
                result_parts.append("会話履歴データは保持されています")
            self._lbl_result.configure(text="\n".join(result_parts))
            self._btn_next.configure(text="閉じる(C)", width=12, command=self.destroy)
            self._btn_cancel.configure(state="disabled")

        if index == 1:
            self._btn_next.configure(state="disabled")
            self._btn_cancel.configure(state="disabled")

    def _on_next(self):
        if self.current_page == 0:
            path = self.install_path.get().strip()
            if not Path(path).exists():
                messagebox.showerror(
                    "フォルダーが見つかりません",
                    f"指定されたフォルダーが存在しません:\n{path}\n\n"
                    "正しいインストール先を指定してください。")
                return
            if not messagebox.askyesno(
                "確認",
                f"以下のフォルダーをアンインストールします。\n\n{path}\n\n"
                "よろしいですか？",
                icon="warning"
            ):
                return
            self._show_page(1)
            threading.Thread(target=self._run_uninstall, daemon=True).start()

    def _on_close(self):
        if self._uninstall_done:
            self.destroy()
            return
        if messagebox.askyesno("キャンセル確認", "アンインストールをキャンセルしますか？"):
            self.destroy()

    def _browse_path(self):
        path = filedialog.askdirectory(title="アンインストール対象フォルダーを選択")
        if path:
            self.install_path.set(os.path.normpath(path))

    # ----------------------------------------------------------
    # アンインストール処理
    # ----------------------------------------------------------
    def _log(self, msg: str):
        self.after(0, lambda m=msg: self._append_log(m))

    def _append_log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _set_progress(self, value: float, label: str = ""):
        self.after(0, lambda: self._progress_var.set(value))
        if label:
            self.after(0, lambda: self._lbl_step.configure(text=label))

    def _run_uninstall(self):
        try:
            install_path = Path(self.install_path.get())

            # ---- Step 1: KBLite プロセス停止 ----
            self._set_progress(10, "KBLite を停止しています...")
            self._log("[1/5] KBLite プロセスを停止しています...")
            self._stop_kblite_process()

            # ---- Step 2: スタートアップ登録削除 ----
            self._set_progress(25, "スタートアップ登録を削除しています...")
            self._log("[2/5] スタートアップ登録を削除しています...")
            self._remove_startup_registry()

            # ---- Step 3: プログラムの追加と削除 登録削除 ----
            self._set_progress(45, "プログラムの追加と削除の登録を削除しています...")
            self._log("[3/5] プログラムの追加と削除の登録を削除しています...")
            self._remove_uninstall_entry()

            # ---- Step 4: ショートカット削除 ----
            self._set_progress(60, "デスクトップショートカットを削除しています...")
            self._log("[4/5] デスクトップショートカットを削除しています...")
            self._remove_desktop_shortcut()

            # ---- Step 5: フォルダー削除 ----
            self._set_progress(75, "インストールフォルダーを削除しています...")
            self._log("[5/5] インストールフォルダーを削除しています...")
            self._remove_install_folder(install_path)

            # ---- Self-Relocation: TEMP側のコピーを後片付け ----
            if "--relocated" in sys.argv:
                self._schedule_temp_cleanup()

            # ---- 完了 ----
            self._set_progress(100, "アンインストール完了")
            self._log("")
            self._log("=" * 50)
            self._log("  KBLite のアンインストールが完了しました")
            self._log("=" * 50)

            self._uninstall_done = True
            self.after(1200, lambda: self._show_page(2))

        except Exception as e:
            import traceback
            self._log(f"\nエラーが発生しました:\n{traceback.format_exc()}")
            self.after(0, lambda: messagebox.showerror(
                "アンインストールエラー",
                f"アンインストール中にエラーが発生しました:\n\n{e}\n\n"
                "ログを確認してください。"))
            self.after(0, lambda: self._btn_next.configure(state="normal"))
            self.after(0, lambda: self._btn_cancel.configure(state="normal"))

    def _stop_kblite_process(self):
        """実行中の KBLite (uvicorn) プロセスを停止する"""
        try:
            # WINDOWTITLE eq KBLite (完全一致) — "KBLite アンインストール" は除外される
            result = subprocess.run(
                ["taskkill", "/F", "/FI", "WINDOWTITLE eq KBLite"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self._log(f"  taskkill: {result.stdout.strip() or '対象プロセスなし'}")
        except Exception as e:
            self._log(f"  プロセス停止スキップ: {e}")

        # uvicorn / python が port 8080 を使用しているか確認して強制終了
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in result.stdout.splitlines():
                if ":8080" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    self._log(f"  PID {pid} を停止しました（ポート 8080）")
        except Exception as e:
            self._log(f"  ポート確認スキップ: {e}")

    def _remove_startup_registry(self):
        """スタートアップレジストリから KBLite を削除する"""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_RUN_KEY,
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
            winreg.CloseKey(key)
            self._log("  スタートアップ登録を削除しました")
        except FileNotFoundError:
            self._log("  スタートアップ登録なし（スキップ）")
        except Exception as e:
            self._log(f"  スタートアップ削除失敗（続行）: {e}")

    def _remove_uninstall_entry(self):
        """プログラムの追加と削除の登録を削除する"""
        try:
            import winreg
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_UNINSTALL_KEY
            )
            self._log("  プログラムの追加と削除の登録を削除しました")
        except FileNotFoundError:
            self._log("  プログラムの追加と削除の登録なし（スキップ）")
        except Exception as e:
            self._log(f"  登録削除失敗（続行）: {e}")

    def _remove_desktop_shortcut(self):
        """デスクトップのショートカットを削除する"""
        try:
            desktop = Path.home() / "Desktop"
            if not desktop.exists():
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
                )
                desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])

            shortcut = desktop / "KBLite.lnk"
            if shortcut.exists():
                shortcut.unlink()
                self._log("  デスクトップショートカットを削除しました")
            else:
                self._log("  デスクトップショートカットなし（スキップ）")
        except Exception as e:
            self._log(f"  ショートカット削除失敗（続行）: {e}")

    def _remove_install_folder(self, install_path: Path):
        """インストールフォルダーを削除する（data/ は keep_data に応じて保持）"""
        # Self-Relocation 済みなら inside_install は False になる（安全ガード）
        if getattr(sys, "frozen", False):
            exe_path = Path(sys.executable).resolve()
            try:
                exe_path.relative_to(install_path.resolve())
                inside_install = True
            except ValueError:
                inside_install = False
        else:
            inside_install = False

        if inside_install:
            self._log("  ※ Self-Relocation が効いていません（バッチ削除にフォールバック）")
            self._schedule_folder_deletion(install_path)
            return

        data_dir = install_path / "data"

        if self.keep_data.get() and data_dir.exists():
            tmp_dir = Path(tempfile.mkdtemp(prefix="kblite_data_"))
            try:
                self._log(f"  会話履歴データを一時保存: {tmp_dir}")
                shutil.copytree(str(data_dir), str(tmp_dir / "data"))

                shutil.rmtree(str(install_path))
                self._log(f"  フォルダー削除完了: {install_path}")

                install_path.mkdir(parents=True, exist_ok=True)
                shutil.copytree(str(tmp_dir / "data"), str(data_dir))
                self._log(f"  会話履歴データを復元: {data_dir}")
            except Exception as e:
                self._log(f"  フォルダー削除失敗: {e}")
                raise
            finally:
                shutil.rmtree(str(tmp_dir), ignore_errors=True)
        else:
            try:
                shutil.rmtree(str(install_path))
                self._log(f"  フォルダー削除完了（データ含む）: {install_path}")
            except Exception as e:
                self._log(f"  フォルダー削除失敗: {e}")
                raise

    def _schedule_folder_deletion(self, folder: Path):
        """プロセス終了後にバッチファイルでフォルダーを強制削除する"""
        self._schedule_folder_deletion_bat(folder)

    def _schedule_folder_deletion_bat(self, folder: Path):
        """アンインストーラーEXEのPID終了を待ってからフォルダーを削除する"""
        my_pid = os.getpid()
        bat_content = (
            "@echo off\n"
            f"set UNINST_PID={my_pid}\n"
            f'set "TARGET={folder}"\n'
            "\n"
            ":waitpid\n"
            'tasklist /FI "PID eq %UNINST_PID%" 2>nul | find "%UNINST_PID%" >nul\n'
            "if not errorlevel 1 (\n"
            "    timeout /t 2 /nobreak >nul\n"
            "    goto waitpid\n"
            ")\n"
            "\n"
            "timeout /t 3 /nobreak >nul\n"
            "\n"
            "set RETRY=0\n"
            ":retry\n"
            'rd /s /q "%TARGET%" 2>nul\n'
            'if not exist "%TARGET%" goto cleanup\n'
            "set /a RETRY+=1\n"
            "if %RETRY% GEQ 10 goto cleanup\n"
            "timeout /t 3 /nobreak >nul\n"
            "goto retry\n"
            "\n"
            ":cleanup\n"
            'del "%~f0"\n'
        )
        import tempfile as _tmpmod
        try:
            with _tmpmod.NamedTemporaryFile(
                suffix=".bat", delete=False, mode="w", encoding="cp932"
            ) as f:
                bat_path = f.name
                f.write(bat_content)
            subprocess.Popen(
                ["cmd", "/c", bat_path],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            self._log(f"  フォルダー削除をスケジュールしました (PID={my_pid} 終了待ち)")
        except Exception as e:
            self._log(f"  削除スケジュール失敗（手動削除が必要）: {e}")

    def _schedule_temp_cleanup(self):
        """Self-Relocation で使った TEMP コピーを後片付けする"""
        if not getattr(sys, "frozen", False):
            return
        my_pid = os.getpid()
        temp_dir = Path(sys.executable).resolve().parent
        bat_content = (
            "@echo off\n"
            f"set PID={my_pid}\n"
            f'set "TARGET={temp_dir}"\n'
            ":wait\n"
            'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul\n'
            "if not errorlevel 1 (\n"
            "    timeout /t 2 /nobreak >nul\n"
            "    goto wait\n"
            ")\n"
            "timeout /t 1 /nobreak >nul\n"
            'rd /s /q "%TARGET%" 2>nul\n'
            'del "%~f0"\n'
        )
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".bat", delete=False, mode="w",
                encoding="cp932", dir=tempfile.gettempdir(),
            ) as f:
                f.write(bat_content)
            subprocess.Popen(
                ["cmd", "/c", f.name],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            self._log("  TEMP クリーンアップをスケジュールしました")
        except Exception as e:
            self._log(f"  TEMP クリーンアップスケジュール失敗: {e}")


# ============================================================
# エントリーポイント
# ============================================================
if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        # Self-Relocation: インストールフォルダ内のEXEから実行された場合、
        # %TEMP% にコピーして再起動する（ファイルロック回避の業界標準手法）
        if "--relocated" not in sys.argv and getattr(sys, "frozen", False):
            exe_path = Path(sys.executable).resolve()
            install_dir = str(exe_path.parent)
            temp_dir = Path(tempfile.gettempdir()) / "kblite_uninstall"
            temp_dir.mkdir(exist_ok=True)
            temp_exe = temp_dir / exe_path.name
            try:
                shutil.copy2(str(exe_path), str(temp_exe))
                subprocess.Popen([
                    str(temp_exe), "--uninstall", "--relocated",
                    f"--target={install_dir}",
                ])
                sys.exit(0)
            except Exception:
                pass  # コピー失敗時はそのまま通常起動
        app = KBLiteUninstaller()
    else:
        app = KBLiteInstaller()
    app.mainloop()
