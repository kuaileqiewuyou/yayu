import json

from core.messaging.stream_parser import LlmResponseStreamParser


def _parse_all(text: str):
    return list(LlmResponseStreamParser().feed(text))


def test_parse_single_dialog_json():
    msgs = _parse_all(json.dumps({
        "character_name": "诺艾尔",
        "speech": "我在这里。",
        "sprite": "0",
    }, ensure_ascii=False))

    assert len(msgs) == 1
    assert msgs[0].name == "诺艾尔"
    assert msgs[0].text == "我在这里。"
    assert msgs[0].asset_id == "0"


def test_parse_multiple_dialog_json_objects():
    raw = "\n".join([
        json.dumps({"character_name": "NARR", "speech": "风吹过窗边。", "sprite": "-1"}, ensure_ascii=False),
        json.dumps({"character_name": "诺艾尔", "speech": "我听见了。", "sprite": "1"}, ensure_ascii=False),
    ])

    msgs = _parse_all(raw)

    assert [m.name for m in msgs] == ["NARR", "诺艾尔"]
    assert [m.text for m in msgs] == ["风吹过窗边。", "我听见了。"]


def test_parse_json_split_across_chunks():
    parser = LlmResponseStreamParser()
    chunks = [
        '{"character_name": "诺',
        '艾尔", "speech": "你好", ',
        '"sprite": "0"}',
    ]

    parsed = []
    for chunk in chunks:
        parsed.extend(parser.feed(chunk))

    assert len(parsed) == 1
    assert parsed[0].name == "诺艾尔"
    assert parsed[0].text == "你好"


def test_parse_markdown_json_fence():
    raw = """```json
{"character_name": "诺艾尔", "speech": "收到。", "sprite": "0"}
```"""

    msgs = _parse_all(raw)

    assert len(msgs) == 1
    assert msgs[0].text == "收到。"


def test_parse_json_array_response():
    raw = json.dumps([
        {"character_name": "NARR", "speech": "清晨。", "sprite": "-1"},
        {"character_name": "诺艾尔", "speech": "早上好。", "sprite": "0"},
    ], ensure_ascii=False)

    msgs = _parse_all(raw)

    assert [m.name for m in msgs] == ["NARR", "诺艾尔"]


def test_parse_dialog_json_with_closing_brace_in_speech():
    raw = json.dumps({
        "character_name": "诺艾尔",
        "speech": "这里有一个右花括号 } 但它只是台词。",
        "sprite": "0",
    }, ensure_ascii=False)

    msgs = _parse_all(raw)

    assert len(msgs) == 1
    assert msgs[0].name == "诺艾尔"
    assert msgs[0].text == "这里有一个右花括号 } 但它只是台词。"


def test_parse_multiple_dialogs_when_first_speech_contains_braces():
    raw = "\n".join([
        json.dumps({
            "character_name": "NARR",
            "speech": "台词里包含 { 和 }，不应截断。",
            "sprite": "-1",
        }, ensure_ascii=False),
        json.dumps({
            "character_name": "诺艾尔",
            "speech": "第二条也要解析。",
            "sprite": "1",
        }, ensure_ascii=False),
    ])

    msgs = _parse_all(raw)

    assert [m.name for m in msgs] == ["NARR", "诺艾尔"]
    assert [m.text for m in msgs] == ["台词里包含 { 和 }，不应截断。", "第二条也要解析。"]


def test_parse_json_array_split_across_chunks():
    parser = LlmResponseStreamParser()
    chunks = [
        '[{"character_name": "NARR", "speech": "清',
        '晨。", "sprite": "-1"}, ',
        '{"character_name": "诺艾尔", "speech": "早上好。", "sprite": "0"}',
        ']',
    ]

    parsed = []
    for chunk in chunks:
        parsed.extend(parser.feed(chunk))

    assert [m.name for m in parsed] == ["NARR", "诺艾尔"]
    assert [m.text for m in parsed] == ["清晨。", "早上好。"]


def test_keeps_incomplete_json_object_until_next_chunk():
    parser = LlmResponseStreamParser()

    assert list(parser.feed('{"character_name": "诺艾尔", "speech": "你好"')) == []
    assert parser.parse_failures == 0

    parsed = list(parser.feed(', "sprite": "0"}'))

    assert len(parsed) == 1
    assert parsed[0].name == "诺艾尔"
    assert parsed[0].text == "你好"
    assert parser.parse_failures == 0
