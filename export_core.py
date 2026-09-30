"""Export one WeChat conversation without loading its history into memory."""

import heapq
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path


MESSAGE_COLUMNS = (
    "local_id, local_type, server_id, real_sender_id, create_time, "
    "message_content, packed_info_data, sort_seq"
)


def _chat_tables(db, chat):
    username = chat["username"]
    md5 = chat["md5"]
    if username != md5:
        return db._msg_conns(username)
    if not re.fullmatch(r"[0-9a-fA-F]{32}", md5):
        return []
    # A contact may have disappeared from the contact index while its message
    # table remains. Locate that table by its already-known hash.
    found = []
    target = "Msg_" + md5.lower()
    try:
        for rel in db._message_dbs():
            conn = db._open(rel)
            try:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (target,)
                ).fetchone()
            except BaseException:
                conn.close()
                raise
            if row:
                found.append((conn, target))
            else:
                conn.close()
    except BaseException:
        for conn, _ in found:
            conn.close()
        raise
    return found


def iter_chat_messages(db, chat):
    """Merge the selected chat's database shards in chronological order."""
    tables = _chat_tables(db, chat)
    if not tables:
        return
    cursors = []
    heap = []
    try:
        for shard, (conn, table) in enumerate(tables):
            cursor = conn.execute(
                f"SELECT {MESSAGE_COLUMNS} FROM {table} "
                "ORDER BY sort_seq ASC, local_id ASC"
            )
            cursors.append(cursor)
            row = cursor.fetchone()
            if row is not None:
                heapq.heappush(heap, (row["sort_seq"], row["local_id"], shard, row))

        nicks = db._nickname_index()
        senders = db._sender_id_index()
        self_name = db.get_self_info().get("nick_name", "我")
        while heap:
            _, _, shard, row = heapq.heappop(heap)
            message = db._export_row(row, {})
            message["sender_name"] = db._resolve_sender(
                row["real_sender_id"], senders, nicks, self_name
            )
            yield message
            next_row = cursors[shard].fetchone()
            if next_row is not None:
                heapq.heappush(
                    heap, (next_row["sort_seq"], next_row["local_id"], shard, next_row)
                )
    finally:
        for cursor in cursors:
            cursor.close()
        seen = set()
        for conn, _ in tables:
            if id(conn) not in seen:
                seen.add(id(conn))
                conn.close()


def plain_content(message):
    kind = str(message.get("type") or "消息")
    content = str(message.get("content") or "").strip()
    if kind == "文本":
        return content or "[空消息]"
    # Encoded media and XML metadata are not useful in a plain-text archive.
    return f"[{kind}]"


def _time_label(value):
    try:
        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OverflowError, OSError):
        return "时间未知"


def export_chat(db, chat, destination, fmt, progress=None, cancelled=None):
    """Atomically export one chat as TXT, JSON, or SQLite."""
    if fmt not in {"txt", "json", "sqlite"}:
        raise ValueError("仅支持 TXT、JSON 或 SQLite")
    destination = Path(destination)
    partial = destination.with_name(destination.name + ".partial")
    if destination.exists() or partial.exists():
        raise FileExistsError("目标文件已存在，请换一个文件名")
    total = 0
    try:
        if fmt == "sqlite":
            conn = sqlite3.connect(partial)
            try:
                conn.execute(
                    "CREATE TABLE chats(md5 TEXT PRIMARY KEY, username TEXT, "
                    "name TEXT, message_count INT)"
                )
                conn.execute(
                    "CREATE TABLE messages(username TEXT, local_id INT, type TEXT, "
                    "type_code INT, sender_id TEXT, sender_name TEXT, create_time INT, "
                    "content TEXT, server_id INT, md5 TEXT, sort_seq INT)"
                )
                conn.execute(
                    "INSERT INTO chats VALUES(?,?,?,?)",
                    (chat["md5"], chat["username"], chat["name"], chat["message_count"]),
                )
                for message in iter_chat_messages(db, chat):
                    if cancelled and cancelled():
                        raise InterruptedError("导出已取消")
                    conn.execute(
                        "INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            chat["username"], message["local_id"], str(message["type"]),
                            message["type_code"], str(message["sender_id"]),
                            message["sender_name"], message["create_time"],
                            message["content"], message["server_id"], message["md5"],
                            message["sort_seq"],
                        ),
                    )
                    total += 1
                    if progress and total % 100 == 0:
                        progress(total)
                conn.commit()
            finally:
                conn.close()
            if cancelled and cancelled():
                raise InterruptedError("导出已取消")
            os.replace(partial, destination)
            return total
        with partial.open("x", encoding="utf-8", newline="\n") as out:
            if fmt == "txt":
                out.write(f"聊天：{chat['name']}\n")
                out.write("格式：简化 TXT（不含图片、语音和文件原件）\n\n")
            else:
                meta = {
                    "wxid": db.wxid,
                    "nick_name": db.get_self_info().get("nick_name", ""),
                    "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "chats": [{
                        "md5": chat["md5"],
                        "username": chat["username"],
                        "name": chat["name"],
                        "message_count": chat["message_count"],
                    }],
                }
                out.write(json.dumps(meta, ensure_ascii=False)[:-1] + ', "messages": [\n')
            for message in iter_chat_messages(db, chat):
                if cancelled and cancelled():
                    raise InterruptedError("导出已取消")
                if fmt == "txt":
                    sender = message["sender_name"] or "未知发送人"
                    content = plain_content(message).replace("\r\n", "\n").replace("\r", "\n")
                    content = content.replace("\n", "\n    ")
                    out.write(f"[{_time_label(message['create_time'])}] {sender}: {content}\n")
                else:
                    if total:
                        out.write(",\n")
                    out.write(json.dumps(dict(message, chat=chat["username"]), ensure_ascii=False))
                total += 1
                if progress and total % 100 == 0:
                    progress(total)
            if fmt == "json":
                out.write("\n]}\n")
        if cancelled and cancelled():
            raise InterruptedError("导出已取消")
        os.replace(partial, destination)
        return total
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
