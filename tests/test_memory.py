import json
import threading

import pytest

from core.memory.store import MemoryStore, split_turns
from core.memory.service import MemoryService
from core.runtime.cancellation import TurnToken, TurnCancelled, turn_scope, check_cancelled
from llm.compact_manager import CompactManager, text_chunks


def dialogue(*texts):
    return [m for text in texts for m in [{"role": "user", "content": text}, {"role": "assistant", "content": "收到"}]]


@pytest.fixture
def store(tmp_path):
    result = MemoryStore(tmp_path / "memory.sqlite3")
    result.ensure_session("a", "alice")
    result.sync_messages("a", dialogue("我喜欢咖啡", "我现在不喝咖啡了"))
    return result


def fact(store, index=0, **changes):
    result = dict(type="preference", topic="咖啡偏好", subject="用户", content="喜欢咖啡", scope="session",
                  certainty="explicit", status="active", source_turn_ids=[store.turns("a")[index]["id"]])
    result.update(changes)
    return result


def commit(store, facts, summaries=None):
    return store.commit_extraction("a", store.session("a")["revision"], facts, summaries or [], len(store.turns("a")))


def test_ids_survive_reload_and_raw_tool_records_are_not_compressed(store):
    before = store.turns("a")
    store.sync_messages("a", dialogue("我喜欢咖啡", "我现在不喝咖啡了"))
    assert [t["id"] for t in store.turns("a")] == [t["id"] for t in before]
    restarted = MemoryStore(store.path)
    assert restarted.turns("a") == before


def test_correction_and_rewind_restore_previous_preference(store):
    commit(store, [fact(store)])
    commit(store, [fact(store, 1, content="现在不喝咖啡")])
    assert [m["content"] for m in store.retrieve("a", "咖啡")] == ["现在不喝咖啡"]
    store.sync_messages("a", dialogue("我喜欢咖啡"))
    assert [m["content"] for m in store.retrieve("a", "咖啡")] == ["喜欢咖啡"]


def test_duplicated_fact_keeps_multiple_sources_and_survives_one_rewind(store):
    commit(store, [fact(store)])
    commit(store, [fact(store, 1)])
    memories = store.list_memories("a")
    assert len(memories) == 1 and len(memories[0]["source_turn_ids"]) == 2
    store.sync_messages("a", dialogue("我喜欢咖啡"))
    assert store.retrieve("a", "咖啡")[0]["content"] == "喜欢咖啡"


def test_late_background_commit_is_rejected_after_rewind_or_clear(store):
    revision = store.session("a")["revision"]
    candidate = fact(store)
    store.sync_messages("a", dialogue("我喜欢咖啡"))
    assert not store.commit_extraction("a", revision, [candidate], [], 2)
    revision = store.session("a")["revision"]
    store.reset("a")
    assert not store.commit_extraction("a", revision, [candidate], [], 2)
    assert store.list_memories("a") == []


def test_appending_does_not_invalidate_extraction_of_previous_turns(store):
    revision = store.session("a")["revision"]
    candidate = fact(store)
    store.sync_messages("a", dialogue("我喜欢咖啡", "我现在不喝咖啡了", "新的一天"))
    assert store.commit_extraction("a", revision, [candidate], [], 2)
    assert store.session("a")["processed"] == 2


def test_parallel_extractors_cannot_commit_an_older_cursor_over_newer_memory(store):
    assert store.commit_extraction("a", 0, [fact(store, 1, content="现在不喝咖啡")], [], 2, expected_processed=0)
    assert not store.commit_extraction("a", 0, [fact(store)], [], 1, expected_processed=0)
    assert store.list_memories("a")[0]["content"] == "现在不喝咖啡"


def test_scope_visibility_and_explicit_global_opt_in(store):
    commit(store, [fact(store, type="event", scope="character")])
    store.ensure_session("b", "alice")
    store.ensure_session("c", "bob")
    assert store.retrieve("b", "咖啡") == []
    store.configure("b", mode="character")
    assert store.retrieve("b", "咖啡")
    store.configure("c", mode="character")
    assert store.retrieve("c", "咖啡") == []
    store.edit("a", fact(store, type="profile", topic="饮品偏好", scope="global"))
    assert store.retrieve("c", "咖啡") == []
    store.configure("c", share_global=True)
    assert store.retrieve("c", "咖啡")[0]["scope"] == "global"


def test_manual_visibility_allows_only_selected_character(store):
    store.edit("a", fact(store, type="event", scope="character", visible_to=["alice", "bob"]))
    store.ensure_session("b", "bob")
    store.configure("b", mode="character")
    assert store.retrieve("b", "咖啡")


def test_inferred_and_completed_facts_are_not_injected_even_if_pinned(store):
    commit(store, [fact(store, certainty="inferred")])
    assert store.list_memories("a")[0]["status"] == "pending"
    assert store.retrieve("a", "咖啡") == []
    store.edit("a", fact(store, certainty="explicit", status="completed", pinned=True))
    assert store.retrieve("a", "咖啡") == []


def test_delete_blocks_paraphrase_and_rebuild_preserves_manual_corrections(store):
    commit(store, [fact(store)])
    memory = store.list_memories("a")[0]
    store.delete(memory["id"])
    store.rebuild("a")
    commit(store, [fact(store, topic="另一个主题键", content="用户爱喝咖啡")])
    assert store.list_memories("a") == []
    store.edit("a", fact(store, topic="手动修正", content="只喝茶", source_turn_ids=[]))
    store.rebuild("a")
    assert store.list_memories("a")[0]["content"] == "只喝茶"


def test_cancelled_incomplete_and_foreign_sources_are_rejected_atomically(store):
    candidate = fact(store)
    store.ensure_session("b", "bob")
    store.sync_messages("b", dialogue("秘密"))
    with pytest.raises(ValueError):
        commit(store, [candidate, fact(store, source_turn_ids=[store.turns("b")[0]["id"]])])
    assert store.list_memories("a") == []
    store.sync_messages("a", dialogue("未完成"), complete=False)
    with pytest.raises(ValueError):
        commit(store, [fact(store)])


def test_retrieval_budget_and_pinned_priority(store):
    for i in range(20):
        store.edit("a", fact(store, topic=f"偏好{i}", content=f"咖啡偏好{i}", pinned=i == 19))
    selected = store.retrieve("a", "咖啡", limit=3, char_budget=2000)
    assert len(selected) <= 3 and selected[0]["pinned"]
    assert store.last_recall("a") == selected


class Extractor:
    def __init__(self):
        self.requests = []

    def generate_stream(self, messages, **kwargs):
        payload = json.loads(messages[-1]["content"])
        self.requests.append(payload)
        return {"content": json.dumps({"summary": "对话中讨论了偏好。", "memories": [{
            "type": "preference", "topic": "咖啡偏好", "content": "喜欢咖啡", "certainty": "explicit",
            "source_turn_ids": [payload["valid_turn_ids"][0]],
        }]}, ensure_ascii=False)}


def test_extraction_batches_and_cursor_avoid_reprocessing(store):
    adapter = Extractor()
    service = MemoryService(store, adapter)
    assert service.extract("a", 0)
    assert len(adapter.requests) == 1
    assert store.session("a")["processed"] == 2
    assert service.extract("a", 0)
    assert len(adapter.requests) == 1
    assert store.list_memories("a")[0]["scope"] == "session"


def test_long_turn_tail_reaches_extractor_without_truncation(store):
    store.sync_messages("a", dialogue("开头" + "正文" * 9000 + "尾部约定：下次带蓝色围巾"))
    adapter = Extractor()
    service = MemoryService(store, adapter)
    service.extract("a", store.session("a")["revision"])
    combined = "".join(p["dialogue"] for p in adapter.requests)
    assert "尾部约定：下次带蓝色围巾" in combined
    assert len(adapter.requests) > 1


def test_empty_or_invalid_extraction_does_not_advance_cursor(store):
    class Bad:
        def generate_stream(self, *args, **kwargs):
            return {"content": '{"summary":"","memories":[]}'}
    service = MemoryService(store, Bad())
    with pytest.raises(ValueError):
        service.extract("a", 0)
    assert store.session("a")["processed"] == 0
    assert store.list_memories("a") == []


def test_background_cancel_is_responsive_and_no_post_cancel_write(store):
    entered = threading.Event()
    class Waiting:
        def generate_stream(self, *args, **kwargs):
            entered.set()
            while True:
                check_cancelled()
                threading.Event().wait(0.01)
    service = MemoryService(store, Waiting())
    try:
        assert service.schedule("a", force=True)
        assert entered.wait(2)
        service.close()
        service.thread.join(2)
        assert not service.is_running()
        assert store.list_memories("a") == []
    finally:
        service.close()


def test_context_keeps_tool_pairs_and_leaves_raw_messages_untouched():
    raw = [{"role": "system", "content": "角色设定"}] + dialogue(*["旧事" * 700 for _ in range(8)])
    raw += [{"role": "user", "content": "搜索"}, {"role": "assistant", "content": "", "tool_calls": [{"id": "x"}]},
            {"role": "tool", "tool_call_id": "x", "content": "结果"}, {"role": "assistant", "content": "答复"}]
    original = json.dumps(raw)
    context = CompactManager(4000).build_context(raw, reply_tokens=800, user_message={"role": "user", "content": "继续"})
    assert json.dumps(raw) == original
    assert len(context) < len(raw)
    assert context[-4:] == raw[-4:]
    assert sum(m.get("role") == "tool" for m in context) == 1
    assert all(turn[0]["role"] == "user" for turn in split_turns(context))


def test_tool_arguments_count_against_budget_and_current_turn_is_never_split():
    messages = [{"role": "user", "content": "请求"}, {"role": "assistant", "content": "", "tool_calls": [{"arguments": "大" * 20000}]}]
    with pytest.raises(ValueError):
        CompactManager(4000).fit_request(messages, reply_tokens=800)


def test_chunking_and_empty_summary_fallback_preserve_original():
    text = "中文" * 10000 + "重要尾部"
    assert "".join(text_chunks(text)) == text
    class Empty:
        def chat(self, **kwargs):
            return {"content": ""}
    messages = dialogue("1", "2", "3", "4", "5")
    assert CompactManager().compact_messages(messages, Empty()) == messages


def test_summary_invalidated_when_any_source_is_rewound(store):
    sources = [t["id"] for t in store.turns("a")]
    commit(store, [], [{"source_turn_ids": sources, "content": "现在不喝咖啡"}])
    store.sync_messages("a", dialogue("我喜欢咖啡"))
    assert store.summaries("a") == []


def test_retry_keeps_user_only_facts_but_not_retracted_story(store):
    commit(store, [fact(store, 1, content="现在不喝咖啡"), fact(store, 1, type="event", topic="书店", content="我们去了书店")])
    last_id = store.turns("a")[-1]["id"]
    store.sync_messages("a", dialogue("我喜欢咖啡"))
    store.retain_user_turn("a", last_id)
    assert [m["content"] for m in store.list_memories("a")] == ["现在不喝咖啡"]
    store.rebuild("a")
    assert store.list_memories("a")[0]["content"] == "现在不喝咖啡"
    store.forget_retained_from("a", 0)
    assert store.list_memories("a") == []


def test_retried_user_statement_edit_invalidates_retained_facts(store):
    commit(store, [fact(store, 1)])
    last_id = store.turns("a")[-1]["id"]
    store.sync_messages("a", dialogue("我喜欢咖啡"))
    store.retain_user_turn("a", last_id)
    store.sync_messages("a", dialogue("我喜欢咖啡", "我其实喜欢茶"))
    assert store.list_memories("a") == []


def test_model_cannot_mark_assistant_guess_as_confirmed_user_preference(store):
    class Guess:
        def generate_stream(self, messages, **kwargs):
            payload = json.loads(messages[-1]["content"])
            return {"content": json.dumps({"summary": "角色猜测了用户的偏好。", "memories": [{
                "type": "preference", "content": "喜欢甜食", "certainty": "explicit", "evidence": "你肯定喜欢甜食",
                "source_turn_ids": payload["valid_turn_ids"],
            }]})}
    store.sync_messages("a", [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你肯定喜欢甜食"}])
    MemoryService(store, Guess()).extract("a", store.session("a")["revision"])
    assert store.list_memories("a")[0]["status"] == "pending"
    assert store.retrieve("a", "甜食") == []
