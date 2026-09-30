import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from export_core import export_chat, iter_chat_messages


CHAT = {"md5": "a" * 32, "username": "test-chat", "name": "测试聊天", "message_count": 3}


class SampleDB:
    wxid = "test-account"

    def _msg_conns(self, _username):
        tables = []
        # Two shards, deliberately interleaved. Text contains Unicode/newlines.
        for rows in (
            [(1, 1, 11, 2, 1700000000, "你好\n第二行", None, 1),
             (2, 34, 13, 3, 1700000002, "encoded media", None, 3)],
            [(1, 1, 12, 3, 1700000001, "收到 😀", None, 2)],
        ):
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            conn.execute("CREATE TABLE Msg_test(local_id, local_type, server_id, real_sender_id, create_time, message_content, packed_info_data, sort_seq)")
            conn.executemany("INSERT INTO Msg_test VALUES(?,?,?,?,?,?,?,?)", rows)
            tables.append((conn, "Msg_test"))
        return tables

    def _nickname_index(self):
        return {"friend": "朋友"}

    def _sender_id_index(self):
        return {3: "friend"}

    def get_self_info(self):
        return {"nick_name": "我"}

    def _resolve_sender(self, sender, index, names, self_name):
        return self_name if sender == 2 else names[index[sender]]

    def _export_row(self, row, _names):
        return {
            "local_id": row["local_id"],
            "type": "文本" if row["local_type"] == 1 else "语音",
            "type_code": row["local_type"],
            "sender_id": row["real_sender_id"],
            "create_time": row["create_time"],
            "content": row["message_content"],
            "server_id": row["server_id"],
            "md5": None,
            "sort_seq": row["sort_seq"],
        }


class ExportTests(unittest.TestCase):
    def test_shards_merge_in_order(self):
        rows = list(iter_chat_messages(SampleDB(), CHAT))
        self.assertEqual([row["server_id"] for row in rows], [11, 12, 13])
        self.assertEqual([row["sender_name"] for row in rows], ["我", "朋友", "朋友"])

    def test_formats_preserve_one_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for fmt in ("txt", "json", "sqlite"):
                count = export_chat(SampleDB(), CHAT, folder / f"chat.{fmt}", fmt)
                self.assertEqual(count, 3)
            text = (folder / "chat.txt").read_text(encoding="utf-8")
            self.assertIn("你好\n    第二行", text)
            self.assertIn("收到 😀", text)
            self.assertIn("[语音]", text)
            self.assertNotIn("encoded media", text)
            payload = json.loads((folder / "chat.json").read_text(encoding="utf-8"))
            self.assertEqual(len(payload["chats"]), 1)
            self.assertEqual([m["server_id"] for m in payload["messages"]], [11, 12, 13])
            with closing(sqlite3.connect(folder / "chat.sqlite")) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM chats").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT count(*) FROM messages").fetchone()[0], 3)

    def test_cancel_removes_incomplete_files(self):
        for fmt in ("txt", "json", "sqlite"):
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"chat.{fmt}"
                calls = 0

                def cancel_after_first():
                    nonlocal calls
                    calls += 1
                    return calls > 1

                with self.assertRaises(InterruptedError):
                    export_chat(SampleDB(), CHAT, path, fmt, cancelled=cancel_after_first)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.txt"
            path.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                export_chat(SampleDB(), CHAT, path, "txt")
            self.assertEqual(path.read_text(encoding="utf-8"), "existing")


if __name__ == "__main__":
    unittest.main()
