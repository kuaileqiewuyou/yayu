"""Confirmed session ownership gates old SQLite memories without rewriting them."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from core.memory.service import MemoryService
from core.memory.store import MemoryStore
from llm.llm_manager import LLMManager


class NoModelCalls:
    def generate_stream(self, *_args, **_kwargs):
        pytest.fail("Ownership checks must complete before calling an extraction model")


def remember(store, session_id, character_id, content, *, topic="咖啡约定"):
    store.ensure_session(session_id, character_id)
    store.sync_messages(session_id, [
        {"role": "user", "content": "记住：" + content},
        {"role": "assistant", "content": "我记住了。"},
    ])
    source_id = store.turns(session_id)[0]["id"]
    candidate = dict(type="event", topic=topic, subject="用户", content=content,
                     scope="character", certainty="explicit", source_turn_ids=[source_id])
    assert store.commit_extraction(session_id, 0, [candidate], [
        {"source_turn_ids": [source_id], "content": "摘要：" + content},
    ], 0)
    return candidate


@pytest.fixture
def journal(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    owners = {"alice-source": "alice", "alice-current": "alice",
              "bob-source": "bob", "bob-current": "bob", "old-bob": "bob"}
    remember(store, "alice-source", "alice", "只对甲说的咖啡约定")
    remember(store, "bob-source", "bob", "只对乙说的咖啡约定")
    # Before character selection existed, a Bob conversation could be saved
    # under the first character's memory ID. The index now knows its true owner.
    remember(store, "old-bob", "alice", "乙的旧秘密咖啡约定")
    for session_id, owner in (("alice-current", "alice"), ("bob-current", "bob")):
        store.ensure_session(session_id, owner)
        store.configure(session_id, mode="character")
    return store, owners


def service_for(store, owners, adapter=None):
    return MemoryService(store, adapter or NoModelCalls(),
                         character_names={"alice": "小芽", "bob": "小芽"},
                         session_owner=lambda session_id: owners.get(session_id, ""))


def manager_for(character="乙"):
    manager = LLMManager(NoModelCalls(), user_template=f"当前角色：{character}")
    manager.set_messages([
        {"role": "system", "content": f"当前角色：{character}"},
        {"role": "user", "content": "本会话原始用户消息"},
        {"role": "assistant", "content": "本会话原始角色回复"},
    ])
    return manager


def text_of(context):
    return json.dumps(context, ensure_ascii=False)


def stored_facts_and_summaries(store):
    with store.connect() as db:
        return {table: [dict(row) for row in db.execute(f"SELECT * FROM {table}")]
                for table in ("facts", "summaries")}


def test_mismatched_current_owner_keeps_raw_messages_without_injecting_memory_or_summary(journal):
    store, owners = journal
    service = service_for(store, owners)
    manager = manager_for()
    original = deepcopy(manager.get_messages())
    before = stored_facts_and_summaries(store)

    context = service.prepare_context("old-bob", manager, "咖啡约定")

    assert context == original
    assert manager.get_messages() == original
    assert "乙的旧秘密" not in text_of(context)
    assert not service.schedule("old-bob", force=True)
    assert not service.extract("old-bob", store.session("old-bob")["revision"])
    assert service.thread is None
    assert stored_facts_and_summaries(store) == before


def test_bad_source_owner_cannot_be_recalled_by_the_character_it_was_mistagged_as(journal):
    store, owners = journal
    before = stored_facts_and_summaries(store)

    recalled = store.retrieve("alice-current", "咖啡约定", session_owner=owners.get)
    context = service_for(store, owners).prepare_context("alice-current", manager_for("甲"), "咖啡约定")

    assert [fact["content"] for fact in recalled] == ["只对甲说的咖啡约定"]
    assert "只对甲说的咖啡约定" in text_of(context)
    assert "乙的旧秘密" not in text_of(context)
    assert stored_facts_and_summaries(store) == before


@pytest.mark.parametrize("session_id, own, other", [
    ("alice-current", "只对甲说的咖啡约定", "只对乙说的咖啡约定"),
    ("bob-current", "只对乙说的咖啡约定", "只对甲说的咖啡约定"),
])
def test_same_named_characters_keep_distinct_stable_memory_owners(journal, session_id, own, other):
    store, owners = journal

    context = service_for(store, owners).prepare_context(session_id, manager_for(), "咖啡约定")

    assert own in text_of(context)
    assert other not in text_of(context)
    assert "乙的旧秘密" not in text_of(context)


def test_bad_newer_fact_does_not_shadow_a_valid_older_fact_with_the_same_topic(journal):
    store, owners = journal
    assert store.retrieve("alice-current", "咖啡约定")[0]["session_id"] == "old-bob"

    recalled = store.retrieve("alice-current", "咖啡约定", session_owner=owners.get)

    assert [fact["session_id"] for fact in recalled] == ["alice-source"]


def test_manual_cross_character_visibility_is_respected_for_confirmed_source(journal):
    store, owners = journal
    source = store.turns("alice-source")[0]["id"]
    store.edit("alice-source", dict(type="event", topic="共享约定", subject="用户",
               content="手动允许乙知道的咖啡约定", scope="character", certainty="explicit",
               source_turn_ids=[source], visible_to=["alice", "bob"]))

    recalled = store.retrieve("bob-current", "咖啡约定", session_owner=owners.get)

    assert "手动允许乙知道的咖啡约定" in {fact["content"] for fact in recalled}
    assert "乙的旧秘密咖啡约定" not in {fact["content"] for fact in recalled}


def test_manual_global_sharing_still_requires_receiver_opt_in_and_confirmed_source(journal):
    store, owners = journal
    for session_id, content in (("alice-source", "允许全局分享的咖啡约定"),
                                ("old-bob", "错归属不应全局分享的咖啡约定")):
        store.edit(session_id, dict(type="profile", topic="全局咖啡", subject="用户", content=content,
                   scope="global", certainty="explicit", source_turn_ids=[]))
    assert all(fact["scope"] != "global" for fact in
               store.retrieve("bob-current", "咖啡约定", session_owner=owners.get))
    store.configure("bob-current", mode="character", share_global=True)

    recalled = store.retrieve("bob-current", "咖啡约定", session_owner=owners.get)

    assert "允许全局分享的咖啡约定" in {fact["content"] for fact in recalled}
    assert "错归属不应全局分享的咖啡约定" not in {fact["content"] for fact in recalled}


def test_unknown_source_owner_is_not_treated_as_permission_to_share(journal):
    store, owners = journal
    owners.pop("old-bob")

    recalled = store.retrieve("alice-current", "咖啡约定", session_owner=owners.get)

    assert [fact["content"] for fact in recalled] == ["只对甲说的咖啡约定"]


@pytest.mark.parametrize("missing", [True, False])
def test_unavailable_or_unconfirmed_current_owner_keeps_only_raw_context(journal, missing):
    store, owners = journal
    if missing:
        owners.pop("alice-source")
        resolve_owner = owners.get
    else:
        def resolve_owner(_session_id):
            raise OSError("session index temporarily unavailable")
    service = MemoryService(store, NoModelCalls(), session_owner=resolve_owner)
    manager = manager_for("甲")

    assert service.prepare_context("alice-source", manager, "咖啡约定") == manager.get_messages()
    assert not service.schedule("alice-source", force=True)
    assert not service.extract("alice-source", store.session("alice-source")["revision"])


def test_owner_change_during_extraction_rejects_late_fact_and_summary_commit(journal):
    store, owners = journal
    before = stored_facts_and_summaries(store)

    class OwnerChangingAdapter:
        def generate_stream(self, messages, **_kwargs):
            payload = json.loads(messages[-1]["content"])
            owners["alice-source"] = "bob"
            return {"content": json.dumps({"summary": "不应提交的摘要", "memories": [{
                "type": "event", "topic": "晚到记忆", "content": "不应提交的事实",
                "certainty": "explicit", "source_turn_ids": payload["valid_turn_ids"],
                "evidence": "只对甲说的咖啡约定",
            }]}, ensure_ascii=False)}

    service = service_for(store, owners, OwnerChangingAdapter())

    assert not service.extract("alice-source", store.session("alice-source")["revision"])
    assert store.session("alice-source")["processed"] == 0
    assert store.session("alice-source")["status"] == "idle"
    assert stored_facts_and_summaries(store) == before


def test_store_commit_rechecks_confirmed_owner_inside_write_transaction(journal):
    store, owners = journal
    source = store.turns("old-bob")[0]["id"]
    before = stored_facts_and_summaries(store)

    assert not store.commit_extraction("old-bob", store.session("old-bob")["revision"], [
        dict(type="event", topic="拒绝提交", content="拒绝提交", source_turn_ids=[source]),
    ], [], 1, session_owner=owners.get)

    assert stored_facts_and_summaries(store) == before
    assert store.session("old-bob")["processed"] == 0


def test_changed_owner_clears_queued_status_without_touching_facts(journal):
    store, owners = journal
    revision = store.session("old-bob")["revision"]
    store.set_status("old-bob", revision, "queued")
    before = stored_facts_and_summaries(store)

    assert not service_for(store, owners).extract("old-bob", revision)

    assert store.session("old-bob")["status"] == "idle"
    assert stored_facts_and_summaries(store) == before


def test_old_fact_owner_is_not_passed_as_existing_memory_after_database_owner_changes(journal):
    store, owners = journal
    with store.connect(write=True) as db:
        db.execute("UPDATE sessions SET character_id='bob' WHERE id='old-bob'")
    requests = []

    class RecordingAdapter:
        def generate_stream(self, messages, **_kwargs):
            payload = json.loads(messages[-1]["content"])
            requests.append(payload)
            return {"content": '{"summary":"按原始聊天整理的摘要","memories":[]}'}

    assert service_for(store, owners, RecordingAdapter()).extract(
        "old-bob", store.session("old-bob")["revision"])

    assert requests and requests[0]["existing"] == []
    assert store.list_memories("old-bob")[0]["character_id"] == "alice"


def test_owner_recheck_discards_memory_and_summary_if_session_changes_while_reading(journal, monkeypatch):
    store, owners = journal
    original_summaries = store.summaries

    def changing_summaries(session_id):
        result = original_summaries(session_id)
        owners[session_id] = "bob"
        return result

    monkeypatch.setattr(store, "summaries", changing_summaries)
    manager = manager_for("甲")

    context = service_for(store, owners).prepare_context("alice-source", manager, "咖啡约定")

    assert context == manager.get_messages()


def test_omitting_owner_callback_preserves_legacy_memory_api(journal):
    store, _owners = journal
    manager = manager_for()

    context = MemoryService(store, NoModelCalls()).prepare_context("old-bob", manager, "咖啡约定")

    assert "乙的旧秘密咖啡约定" in text_of(context)
    assert "摘要：乙的旧秘密咖啡约定" in text_of(context)
