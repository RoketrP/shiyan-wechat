"""Local window for importing and exporting one WeChat conversation."""

import threading
import queue
import re
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from wechatauto import WeChatDB, list_accounts

from export_core import export_chat, plain_content


class ExportWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("拾言 · 微信聊天记录")
        self.root.geometry("1100x780")
        self.root.minsize(900, 650)
        self.status = tk.StringVar(value="正在读取当前登录的微信账号…")
        self.search = tk.StringVar()
        self.account_label = tk.StringVar()
        self.format = tk.StringVar(value="txt")
        self.chats = []
        self.accounts = []
        self.active_account = None
        self.visible_chats = []
        self.selected = None
        self.imported = None
        self.busy = False
        self.cancel_event = threading.Event()
        self.ui_queue = queue.Queue()

        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="拾言 · 微信聊天记录", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
        ttk.Label(frame, text="选择一个聊天，点击“导入并预览”，再导出完整记录。", padding=(0, 7)).pack(anchor="w")
        account_row = ttk.Frame(frame)
        account_row.pack(fill="x", pady=(0, 7))
        ttk.Label(account_row, text="微信账号：").pack(side="left")
        self.account_box = ttk.Combobox(account_row, textvariable=self.account_label, state="disabled", width=35)
        self.account_box.pack(side="left")
        self.account_box.bind("<<ComboboxSelected>>", self.choose_account)
        ttk.Label(frame, textvariable=self.status, wraplength=780).pack(anchor="w", pady=(0, 10))

        ttk.Label(frame, text="TXT 中的图片、语音、文件等显示为类型标记，不包含媒体原件。", foreground="#785b20").pack(side="bottom", anchor="w", pady=(6, 0))
        controls = ttk.Frame(frame)
        controls.pack(side="bottom", fill="x", pady=(12, 4))
        self.import_button = ttk.Button(controls, text="导入并预览", command=self.start_import, state="disabled")
        self.import_button.pack(side="left")
        ttk.Label(controls, text="  导出格式：").pack(side="left")
        ttk.Radiobutton(controls, text="简化 TXT", variable=self.format, value="txt").pack(side="left")
        ttk.Radiobutton(controls, text="JSON", variable=self.format, value="json").pack(side="left", padx=(10, 0))
        ttk.Radiobutton(controls, text="SQLite", variable=self.format, value="sqlite").pack(side="left", padx=(10, 0))
        self.export_button = ttk.Button(controls, text="导出选中聊天", command=self.start_export, state="disabled")
        self.export_button.pack(side="right")
        self.cancel_button = ttk.Button(controls, text="取消导出", command=self.cancel_export, state="disabled")
        self.cancel_button.pack(side="right", padx=(0, 8))

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=False, padx=(0, 12))
        ttk.Label(left, text="搜索聊天").pack(anchor="w")
        ttk.Entry(left, textvariable=self.search, width=32).pack(fill="x", pady=(4, 8))
        self.search.trace_add("write", lambda *_: self.filter_chats())
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, width=35, exportselection=False)
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.choose_chat)
        scrollbar = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="最近消息预览（最多 50 条）").pack(anchor="w")
        preview_frame = ttk.Frame(right)
        preview_frame.pack(fill="both", expand=True, pady=(4, 0))
        self.preview = tk.Text(preview_frame, wrap="word", state="disabled", font=("Microsoft YaHei UI", 9))
        self.preview.pack(side="left", fill="both", expand=True)
        preview_scroll = ttk.Scrollbar(preview_frame, command=self.preview.yview)
        preview_scroll.pack(side="right", fill="y")
        self.preview.configure(yscrollcommand=preview_scroll.set)

        self.root.after(50, self.drain_ui_queue)
        threading.Thread(target=self.load_initial, daemon=True).start()

    def on_ui(self, callback):
        self.ui_queue.put(callback)

    def drain_ui_queue(self):
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(50, self.drain_ui_queue)

    def set_preview(self, value):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("end", value)
        self.preview.configure(state="disabled")

    def set_busy(self, busy, exporting=False):
        self.busy = busy
        self.account_box.configure(state="disabled" if busy or not self.accounts else "readonly")
        self.import_button.configure(state="disabled" if busy or not self.selected else "normal")
        self.export_button.configure(state="disabled" if busy or not self.imported else "normal")
        self.cancel_button.configure(state="normal" if exporting else "disabled")

    def make_db(self, account):
        return WeChatDB(account=account)

    def load_initial(self):
        try:
            accounts = list_accounts()
            if not accounts:
                raise RuntimeError("没有找到微信账号目录")
            account = accounts[0]["account"]
            chats = self.make_db(account).list_message_chats()
            self.on_ui(lambda: self.show_initial(accounts, account, chats))
        except Exception as exc:
            self.on_ui(lambda exc=exc: self.status.set(f"读取失败：{exc}"))

    def show_initial(self, accounts, account, chats):
        self.accounts = accounts
        self.account_box.configure(values=[a["wxid"] for a in accounts])
        self.account_box.current(0)
        self.active_account = account
        self.show_chats(chats)
        self.set_busy(False)

    def choose_account(self, _event=None):
        if self.busy:
            return
        index = self.account_box.current()
        if index < 0:
            return
        account = self.accounts[index]["account"]
        if account == self.active_account:
            return
        self.active_account = account
        self.chats = []
        self.filter_chats()
        self.set_busy(True)
        self.status.set("正在读取所选微信账号…")
        threading.Thread(target=self.load_account, args=(account,), daemon=True).start()

    def load_account(self, account):
        try:
            chats = self.make_db(account).list_message_chats()
            self.on_ui(lambda: self.finish_load_account(account, chats))
        except Exception as exc:
            self.on_ui(lambda exc=exc: self.fail("读取账号失败", exc))

    def finish_load_account(self, account, chats):
        if self.active_account == account:
            self.show_chats(chats)
        self.set_busy(False)

    def show_chats(self, chats):
        self.chats = chats
        self.status.set(f"已读取 {len(chats)} 个有消息的聊天。请选择一个聊天。")
        self.filter_chats()

    def filter_chats(self):
        term = self.search.get().strip().casefold()
        self.visible_chats = [
            chat for chat in self.chats
            if term in str(chat["name"]).casefold() or term in str(chat["username"]).casefold()
        ]
        self.listbox.delete(0, "end")
        for chat in self.visible_chats:
            self.listbox.insert("end", f"{chat['name']}  ({chat['message_count']} 条)")
        self.selected = None
        self.imported = None
        self.set_busy(self.busy)
        self.set_preview("")

    def choose_chat(self, _event=None):
        selection = self.listbox.curselection()
        self.selected = self.visible_chats[selection[0]] if selection else None
        self.imported = None
        self.set_preview("")
        self.set_busy(self.busy)
        if self.selected:
            self.status.set(f"已选择：{self.selected['name']}。点击“导入并预览”。")

    def start_import(self):
        if self.busy or not self.selected:
            return
        chat = self.selected.copy()
        self.set_busy(True)
        self.status.set(f"正在导入 {chat['name']} 的最近消息…")
        threading.Thread(target=self.import_chat, args=(chat, self.active_account), daemon=True).start()

    def import_chat(self, chat, account):
        try:
            db = self.make_db(account)
            messages = db.get_messages(chat["username"], limit=50)
            nicknames = db.nickname_map()
            self_name = db.get_self_info().get("nick_name", "我")
            lines = []
            for message in reversed(messages):
                try:
                    when = datetime.fromtimestamp(int(message["create_time"])).strftime("%Y-%m-%d %H:%M")
                except (TypeError, ValueError, OverflowError, OSError):
                    when = "时间未知"
                username = message.get("sender_username")
                sender = self_name if message.get("sender_id") == 2 else (
                    nicknames.get(username, username) if username else "对方/群成员"
                )
                lines.append(f"[{when}] {sender}\n{plain_content(message)}\n")
            self.on_ui(lambda: self.finish_import(chat, "\n".join(lines)))
        except Exception as exc:
            self.on_ui(lambda exc=exc: self.fail("导入失败", exc))

    def finish_import(self, chat, preview):
        self.set_busy(False)
        if self.selected and self.selected["md5"] == chat["md5"]:
            self.imported = chat
            self.set_preview(preview or "这个聊天暂时没有可预览的消息。")
            self.status.set(f"已导入 {chat['name']}，共 {chat['message_count']} 条消息，可导出完整记录。")
            self.set_busy(False)

    def start_export(self):
        if self.busy or not self.imported:
            return
        chat = self.imported.copy()
        fmt = self.format.get()
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(chat["name"]))
        safe_name = safe_name.strip(" .")[:80] or "聊天"
        suggested = f"{safe_name}-聊天记录.{fmt}"
        file_types = {
            "txt": [("文本文件", "*.txt")],
            "json": [("JSON 文件", "*.json")],
            "sqlite": [("SQLite 数据库", "*.sqlite")],
        }
        path = filedialog.asksaveasfilename(
            title="保存选中聊天", initialfile=suggested,
            defaultextension=f".{fmt}",
            filetypes=file_types[fmt],
        )
        if not path:
            return
        destination = Path(path)
        if destination.exists():
            messagebox.showerror("无法导出", "这个文件已存在，请换一个文件名。")
            return
        self.cancel_event.clear()
        self.set_busy(True, exporting=True)
        self.status.set("正在导出第 0 条消息…")
        threading.Thread(target=self.export, args=(chat, destination, fmt, self.active_account), daemon=True).start()

    def export(self, chat, destination, fmt, account):
        try:
            db = self.make_db(account)
            count = export_chat(
                db, chat, destination, fmt,
                progress=lambda n: self.on_ui(lambda n=n: self.status.set(f"正在导出第 {n} 条消息…")),
                cancelled=self.cancel_event.is_set,
            )
            self.on_ui(lambda: self.finish_export(destination, count))
        except InterruptedError:
            self.on_ui(lambda: self.finish_cancel())
        except Exception as exc:
            self.on_ui(lambda exc=exc: self.fail("导出失败", exc))

    def finish_export(self, destination, count):
        self.set_busy(False)
        self.status.set(f"导出完成，共 {count} 条消息。")
        messagebox.showinfo("导出完成", f"已保存 {count} 条消息。\n\n{destination}")

    def cancel_export(self):
        self.cancel_event.set()
        self.status.set("正在取消导出…")

    def finish_cancel(self):
        self.set_busy(False)
        self.status.set("导出已取消，未保存不完整的文件。")

    def fail(self, title, exc):
        self.set_busy(False)
        self.status.set(f"{title}：{exc}")
        messagebox.showerror(title, str(exc))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ExportWindow().run()
