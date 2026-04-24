#!/usr/bin/env python3
"""
KBLite アンインストーラー
Windows GUI ウィザード形式アンインストーラー
"""

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.scrolledtext as st
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# ============================================================
# 定数
# ============================================================
APP_NAME = "KBLite"
APP_VERSION = "1.0.0"
DEFAULT_INSTALL_PATH = r"C:\KBLite"

REGISTRY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "KBLite"
REGISTRY_UNINSTALL_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\KBLite"
)


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
        self.install_path = tk.StringVar(value=self._detect_install_path())
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
        # EXEとして実行中かつそのEXEがインストールフォルダー内にある場合は遅延削除
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
            if self.keep_data.get():
                self._log("  ※ EXEから実行しているためデータ保持は無効です（全削除します）")
            self._log(f"  プロセス終了後にバッチで削除をスケジュールします: {install_path}")
            self._schedule_folder_deletion(install_path)
            return

        data_dir = install_path / "data"

        if self.keep_data.get() and data_dir.exists():
            # data/ を一時退避 → フォルダー削除 → data/ を復元
            import tempfile
            tmp_dir = Path(tempfile.mkdtemp(prefix="kblite_data_"))
            try:
                self._log(f"  会話履歴データを一時保存: {tmp_dir}")
                shutil.copytree(str(data_dir), str(tmp_dir / "data"))

                shutil.rmtree(str(install_path), ignore_errors=False)
                self._log(f"  フォルダー削除完了: {install_path}")

                # データを元の場所に復元
                install_path.mkdir(parents=True, exist_ok=True)
                shutil.copytree(str(tmp_dir / "data"), str(data_dir))
                self._log(f"  会話履歴データを復元: {data_dir}")
            finally:
                shutil.rmtree(str(tmp_dir), ignore_errors=True)
        else:
            shutil.rmtree(str(install_path), ignore_errors=False)
            self._log(f"  フォルダー削除完了（データ含む）: {install_path}")

    def _schedule_folder_deletion(self, folder: Path):
        """プロセス終了後にフォルダーを削除する一時バッチを起動する"""
        bat_content = (
            "@echo off\n"
            "timeout /t 3 /nobreak >nul\n"
            f'rd /s /q "{folder}"\n'
            f'if exist "{folder}" (\n'
            "  timeout /t 3 /nobreak >nul\n"
            f'  rd /s /q "{folder}"\n'
            ")\n"
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
                close_fds=True,
            )
            self._log("  フォルダー削除をスケジュールしました")
        except Exception as e:
            self._log(f"  バッチ起動失敗（手動削除が必要）: {e}")


# ============================================================
# エントリーポイント
# ============================================================
if __name__ == "__main__":
    app = KBLiteUninstaller()
    app.mainloop()
