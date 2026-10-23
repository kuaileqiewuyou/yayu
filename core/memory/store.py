"""SQLite memory journal. Each operation owns its connection and transaction.

Facts are versioned rather than overwritten. Removing source turns exposes the
previous valid version; tombstones and manual edits survive a rebuild.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4


TYPES = {"profile", "preference", "event", "relationship", "promise", "state", "item"}
SCOPES = {"session", "character", "global"}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def split_turns(messages):
    """A user message starts a turn; tool calls/results stay with their owner."""
    turns = []
    for message in messages:
        if message.get("role") == "system":
            continue
        if message.get("role") == "user" or not turns:
            turns.append([])
        turns[-1].append(message)
    return turns


def terms(text):
    text = text.lower()
    words = set(re.findall(r"[a-z0-9_]+", text))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        words.update(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return words


def session_owner_matches(session_owner, session_id, character_id):
    """Check stable ownership without rewriting possibly misattributed history."""
    if session_owner is None:
        return True
    try:
        expected_owner = session_owner(session_id)
    except Exception:
        # An unavailable or ambiguous session record cannot authorize recall.
        return False
    return bool(expected_owner) and expected_owner == character_id


class MemoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, character_id TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT 'fresh', share_global INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 0, processed INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'idle', error TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, position INTEGER NOT NULL,
                    messages TEXT NOT NULL, complete INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1);
                CREATE INDEX IF NOT EXISTS turn_session ON turns(session_id,active,position);
                CREATE TABLE IF NOT EXISTS facts (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    session_id TEXT NOT NULL, character_id TEXT NOT NULL, topic TEXT NOT NULL,
                    data TEXT NOT NULL, manual INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS fact_session ON facts(session_id,seq);
                CREATE TABLE IF NOT EXISTS tombstones (
                    session_id TEXT NOT NULL, topic TEXT NOT NULL, PRIMARY KEY(session_id,topic));
                CREATE TABLE IF NOT EXISTS summaries (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    source_ids TEXT NOT NULL, content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS recalls (
                    session_id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS retained_user_sources (
                    turn_id TEXT PRIMARY KEY, session_id TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def ensure_session(self, session_id, character_id=""):
        with self.connect(write=True) as db:
            db.execute("INSERT OR IGNORE INTO sessions(id,character_id) VALUES (?,?)", (session_id, character_id))
            if character_id:
                db.execute("UPDATE sessions SET character_id=? WHERE id=? AND character_id=''", (character_id, session_id))
        return self.session(session_id)

    def session(self, session_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            return dict(row) if row else None

    def configure(self, session_id, *, mode="fresh", share_global=False):
        if mode not in {"fresh", "character"}:
            raise ValueError("未知记忆继承方式")
        with self.connect(write=True) as db:
            db.execute("UPDATE sessions SET mode=?,share_global=?,revision=revision+1 WHERE id=?",
                       (mode, int(share_global), session_id))

    def sync_messages(self, session_id, messages, *, complete=True, last_turn_id=None):
        """Import legacy logs and reconcile rewinds using the common turn prefix.

        New turns do not invalidate a running extraction of earlier turns.
        Edits/rewinds do: all background commits check the session revision.
        """
        self.ensure_session(session_id)
        groups = split_turns(messages)
        with self.connect(write=True) as db:
            old = db.execute("SELECT * FROM turns WHERE session_id=? AND active=1 ORDER BY position", (session_id,)).fetchall()
            common = 0
            while common < min(len(old), len(groups)) and old[common]["messages"] == encode(groups[common]):
                common += 1
            if common < len(old):
                db.execute("UPDATE turns SET active=0 WHERE session_id=? AND position>=?", (session_id, common))
                db.execute("UPDATE sessions SET revision=revision+1,processed=0,status='idle',error='' WHERE id=?", (session_id,))
                db.execute("DELETE FROM summaries WHERE session_id=?", (session_id,))
                db.execute("DELETE FROM recalls WHERE session_id=?", (session_id,))
                db.execute("DELETE FROM retained_user_sources WHERE turn_id IN (SELECT id FROM turns WHERE session_id=? AND position>=?)", (session_id, common))
            for position in range(common, len(groups)):
                group = groups[position]
                finished = (complete or position < len(groups) - 1) and group[-1].get("role") == "assistant"
                if any("[本轮已停止" in str(m.get("content", "")) for m in group):
                    finished = False
                turn_id = last_turn_id if position == len(groups) - 1 and last_turn_id else uuid4().hex
                # A repeated sync after cancellation may already have used this id.
                if db.execute("SELECT 1 FROM turns WHERE id=?", (turn_id,)).fetchone():
                    turn_id = uuid4().hex
                db.execute("INSERT INTO turns(id,session_id,position,messages,complete) VALUES (?,?,?,?,?)",
                           (turn_id, session_id, position, encode(group), int(finished)))
            # A retry may retain user-only evidence, but changing the retried
            # user statement invalidates it.
            retained = db.execute("SELECT t.* FROM turns t JOIN retained_user_sources r ON t.id=r.turn_id WHERE t.session_id=?", (session_id,)).fetchall()
            for row in retained:
                if row["position"] < len(groups):
                    previous = json.loads(row["messages"])[0].get("content", "")
                    current = groups[row["position"]][0].get("content", "")
                    normalize = lambda text: re.sub(r"^\[本地时间 [^\]]+\]\n", "", str(text))
                    if normalize(previous) != normalize(current):
                        db.execute("DELETE FROM retained_user_sources WHERE turn_id=?", (row["id"],))
            if common == len(groups) and groups and not complete:
                db.execute("UPDATE turns SET complete=0 WHERE session_id=? AND active=1 AND position=?", (session_id, len(groups) - 1))

    def turns(self, session_id):
        with self.connect() as db:
            return [dict(row) | {"messages": json.loads(row["messages"])} for row in db.execute(
                "SELECT * FROM turns WHERE session_id=? AND active=1 ORDER BY position", (session_id,))]

    def source(self, turn_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone()
            retained = db.execute("SELECT 1 FROM retained_user_sources WHERE turn_id=?", (turn_id,)).fetchone()
            return dict(row) | {"messages": json.loads(row["messages"]), "user_retained": bool(retained)} if row else None

    def retain_user_turn(self, session_id, turn_id):
        with self.connect(write=True) as db:
            db.execute("INSERT OR IGNORE INTO retained_user_sources VALUES (?,?)", (turn_id, session_id))
            db.execute("UPDATE sessions SET revision=revision+1 WHERE id=?", (session_id,))

    def forget_retained_from(self, session_id, position):
        with self.connect(write=True) as db:
            db.execute("DELETE FROM retained_user_sources WHERE turn_id IN (SELECT id FROM turns WHERE session_id=? AND position>=?)", (session_id, position))
            db.execute("UPDATE sessions SET revision=revision+1 WHERE id=?", (session_id,))

    def _effective(self, db):
        active = {r["id"] for r in db.execute("SELECT id FROM turns WHERE active=1 AND complete=1")}
        user_sources = {r["turn_id"] for r in db.execute("SELECT turn_id FROM retained_user_sources")}
        deleted = {(r["session_id"], r["topic"]) for r in db.execute("SELECT * FROM tombstones")}
        latest = {}
        for row in db.execute("SELECT * FROM facts ORDER BY seq"):
            key = (row["session_id"], row["topic"])
            data = json.loads(row["data"])
            sources = data.get("source_turn_ids", [])
            valid_sources = active | user_sources if data["type"] in {"profile", "preference"} else active
            if key in deleted or (sources and not valid_sources.intersection(sources)):
                continue
            previous = latest.get(key)
            if previous and previous["manual"] and not row["manual"]:
                continue
            latest[key] = dict(row) | {"data": data}
        return sorted(latest.values(), key=lambda row: row["seq"])

    def list_memories(self, session_id=None):
        with self.connect() as db:
            rows = self._effective(db)
            return [r["data"] | {"id": r["id"], "session_id": r["session_id"],
                                  "character_id": r["character_id"], "manual": bool(r["manual"])}
                    for r in rows if session_id is None or r["session_id"] == session_id]

    def _insert_fact(self, db, session, fact, *, manual=False):
        kind = fact.get("type", "event")
        if kind not in TYPES or not isinstance(fact.get("content"), str) or not fact["content"].strip():
            raise ValueError("记忆类型或内容无效")
        scope = fact.get("scope", "session")
        if scope not in SCOPES or (scope == "global" and not manual):
            raise ValueError("全局记忆需要用户明确设置")
        topic = str(fact.get("topic") or fact["content"]).strip()[:200]
        topic = kind + ":" + re.sub(r"\s+", "", topic).lower()
        sources = list(dict.fromkeys(fact.get("source_turn_ids", [])))
        if not manual:
            # Block paraphrases derived from the same deleted evidence too,
            # even if the extractor chooses a different topic label on rebuild.
            for removed in db.execute("SELECT f.data FROM facts f JOIN tombstones t ON f.session_id=t.session_id AND f.topic=t.topic WHERE f.session_id=?", (session["id"],)):
                data = json.loads(removed["data"])
                if data["type"] == kind and set(sources).intersection(data["source_turn_ids"]):
                    return None
        if not manual and not sources:
            raise ValueError("自动记忆缺少原始对话出处")
        valid = {r["id"] for r in db.execute("SELECT id FROM turns WHERE session_id=? AND active=1 AND complete=1", (session["id"],))}
        if manual and kind in {"profile", "preference"}:
            valid |= {r["turn_id"] for r in db.execute("SELECT turn_id FROM retained_user_sources WHERE session_id=?", (session["id"],))}
        if any(source not in valid for source in sources):
            raise ValueError("记忆来源已撤销或不属于当前存档")
        certainty = fact.get("certainty", "inferred")
        if certainty not in {"explicit", "inferred"}:
            raise ValueError("记忆确定性无效")
        status = fact.get("status", "active")
        if status not in {"active", "completed", "cancelled", "pending"}:
            raise ValueError("记忆状态无效")
        # Extraction can only give the current character knowledge. Additional
        # visibility or global sharing must be explicitly edited in the UI.
        visible = fact.get("visible_to", [session["character_id"]]) if manual else [session["character_id"]]
        data = {
            "type": kind, "topic": topic.split(":", 1)[1], "scope": scope,
            "subject": str(fact.get("subject", ""))[:200], "content": fact["content"].strip()[:2000],
            "source_turn_ids": sources, "certainty": certainty,
            "status": "pending" if certainty == "inferred" else status,
            "importance": max(1, min(5, int(fact.get("importance", 3)))),
            "pinned": bool(fact.get("pinned", False)) if manual else False,
            "visible_to": visible, "created_at": fact.get("created_at", now()), "updated_at": now(),
        }
        # Keep supporting sources for identical facts, without treating evidence
        # for an old preference as evidence for its corrected value.
        for previous in self._effective(db):
            if previous["session_id"] == session["id"] and previous["topic"] == topic and previous["data"]["content"] == data["content"]:
                data["source_turn_ids"] = sorted(set(data["source_turn_ids"]) | (set(previous["data"]["source_turn_ids"]) & valid))
        memory_id = uuid4().hex
        db.execute("INSERT INTO facts(id,session_id,character_id,topic,data,manual) VALUES (?,?,?,?,?,?)",
                   (memory_id, session["id"], session["character_id"], topic, encode(data), int(manual)))
        return memory_id

    def commit_extraction(self, session_id, revision, facts, summaries, processed, *, expected_processed=None,
                          session_owner=None):
        with self.connect(write=True) as db:
            from core.runtime.cancellation import check_cancelled
            check_cancelled()
            session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if session is None or session["revision"] != revision:
                return False
            if not session_owner_matches(session_owner, session_id, session["character_id"]):
                return False
            if expected_processed is not None and session["processed"] != expected_processed:
                return False
            for fact in facts:
                self._insert_fact(db, session, fact)
            valid = {r["id"] for r in db.execute("SELECT id FROM turns WHERE session_id=? AND active=1 AND complete=1", (session_id,))}
            for summary in summaries:
                if not summary["source_turn_ids"] or not set(summary["source_turn_ids"]) <= valid:
                    raise ValueError("摘要来源无效")
                if not isinstance(summary["content"], str) or not summary["content"].strip():
                    raise ValueError("摘要不能为空")
                db.execute("INSERT INTO summaries(session_id,source_ids,content) VALUES (?,?,?)",
                           (session_id, encode(summary["source_turn_ids"]), summary["content"].strip()[:6000]))
            db.execute("UPDATE sessions SET processed=MAX(processed,?),status='ready',error='',updated_at=? WHERE id=?",
                       (processed, now(), session_id))
            return True

    def summaries(self, session_id):
        with self.connect() as db:
            valid = {r["id"] for r in db.execute("SELECT id FROM turns WHERE session_id=? AND active=1 AND complete=1", (session_id,))}
            return [{"source_turn_ids": json.loads(r["source_ids"]), "content": r["content"]}
                    for r in db.execute("SELECT * FROM summaries WHERE session_id=? ORDER BY seq", (session_id,))
                    if set(json.loads(r["source_ids"])) <= valid]

    def edit(self, session_id, fact):
        with self.connect(write=True) as db:
            session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if session is None:
                raise ValueError("存档不存在")
            memory_id = self._insert_fact(db, session, fact, manual=True)
            if fact.get("id"):
                previous = db.execute("SELECT * FROM facts WHERE id=? AND session_id=?", (fact["id"], session_id)).fetchone()
                current = db.execute("SELECT topic FROM facts WHERE id=?", (memory_id,)).fetchone()
                if previous and previous["topic"] != current["topic"]:
                    db.execute("INSERT OR IGNORE INTO tombstones VALUES (?,?)", (session_id, previous["topic"]))
            db.execute("DELETE FROM summaries WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM recalls WHERE session_id=?", (session_id,))
            db.execute("UPDATE sessions SET revision=revision+1 WHERE id=?", (session_id,))
            return memory_id

    def delete(self, memory_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM facts WHERE id=?", (memory_id,)).fetchone()
            if row:
                db.execute("INSERT OR IGNORE INTO tombstones VALUES (?,?)", (row["session_id"], row["topic"]))
                # Summaries may still mention a deleted fact. Drop derived
                # summaries and rebuild only after applying tombstones.
                db.execute("DELETE FROM summaries WHERE session_id=?", (row["session_id"],))
                db.execute("DELETE FROM recalls WHERE session_id=?", (row["session_id"],))
                db.execute("UPDATE sessions SET revision=revision+1 WHERE id=?", (row["session_id"],))

    def blocked_topics(self, session_id):
        with self.connect() as db:
            return [r["topic"] for r in db.execute("SELECT topic FROM tombstones WHERE session_id=?", (session_id,))]

    def reset(self, session_id, *, delete_session=False):
        with self.connect(write=True) as db:
            db.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
            for table in ("facts", "summaries", "recalls", "tombstones", "retained_user_sources"):
                db.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
            db.execute("UPDATE sessions SET revision=revision+1,processed=0,status='idle',error='' WHERE id=?", (session_id,))
            if delete_session:
                db.execute("DELETE FROM sessions WHERE id=?", (session_id,))

    def rebuild(self, session_id):
        with self.connect(write=True) as db:
            db.execute("DELETE FROM summaries WHERE session_id=?", (session_id,))
            # Retain deleted evidence so a renamed/paraphrased extraction cannot
            # resurrect it after rebuilding.
            retained = {r["turn_id"] for r in db.execute("SELECT turn_id FROM retained_user_sources WHERE session_id=?", (session_id,))}
            rows = db.execute("SELECT id,data FROM facts WHERE session_id=? AND manual=0 AND topic NOT IN (SELECT topic FROM tombstones WHERE session_id=?)", (session_id, session_id)).fetchall()
            for row in rows:
                data = json.loads(row["data"])
                if data["type"] not in {"profile", "preference"} or not retained.intersection(data["source_turn_ids"]):
                    db.execute("DELETE FROM facts WHERE id=?", (row["id"],))
            db.execute("UPDATE sessions SET revision=revision+1,processed=0,status='idle',error='' WHERE id=?", (session_id,))

    def set_status(self, session_id, revision, status, error=""):
        with self.connect(write=True) as db:
            db.execute("UPDATE sessions SET status=?,error=? WHERE id=? AND revision=?", (status, error[:400], session_id, revision))

    def retrieve(self, session_id, query, *, limit=12, char_budget=3500, session_owner=None):
        session = self.session(session_id)
        if session is None or not session_owner_matches(session_owner, session_id, session["character_id"]):
            return []
        words = terms(query)
        matches = []
        seen_topics = set()
        # Newer facts about the same subject/topic override older shared facts.
        # Scope and visibility are checked before claiming a topic.
        for fact in reversed(self.list_memories()):
            if not session_owner_matches(session_owner, fact["session_id"], fact["character_id"]):
                continue
            own = fact["session_id"] == session_id
            shared = (fact["scope"] == "character" and session["mode"] == "character"
                      and session["character_id"] in fact["visible_to"])
            global_ok = fact["scope"] == "global" and session["share_global"]
            if not (own or shared or global_ok):
                continue
            if not global_ok and session["character_id"] not in fact["visible_to"]:
                continue
            topic_key = (fact["type"], fact["subject"], fact["topic"])
            if topic_key in seen_topics:
                continue
            if fact["certainty"] == "explicit":
                seen_topics.add(topic_key)
            if fact["status"] != "active" or fact["certainty"] != "explicit":
                continue
            overlap = len(words & terms(fact["content"] + fact["subject"] + fact["topic"]))
            ongoing = fact["type"] in {"state", "promise"} and own
            if not (overlap or fact["pinned"] or ongoing):
                continue
            matches.append((overlap * 4 + fact["importance"] + 20 * fact["pinned"] + 5 * ongoing, fact))
        result = []
        for _, fact in sorted(matches, key=lambda pair: (pair[0], pair[1]["updated_at"]), reverse=True):
            if len(result) >= limit:
                break
            cost = len(encode(fact))
            if cost <= char_budget:
                result.append(fact)
                char_budget -= cost
        with self.connect(write=True) as db:
            db.execute("INSERT OR REPLACE INTO recalls VALUES (?,?)", (session_id, encode(result)))
        return result

    def last_recall(self, session_id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM recalls WHERE session_id=?", (session_id,)).fetchone()
            return json.loads(row["data"]) if row else []
