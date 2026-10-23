from core.messaging.template_output_validator import validate_template_output


def test_validate_template_output_accepts_valid_multiline_json_objects():
    text = '\n'.join([
        '{"character_name":"NARR","speech":"夕阳落下。","sprite":"-1"}',
        '{"character_name":"小夏","speech":"我们回家吧。","sprite":"1"}',
        '{"character_name":"CHOICE","speech":"一起回家/再待一会儿","sprite":"-1"}',
        '{"character_name":"CG","speech":"夕阳下的教室，galgame CG","sprite":"-1"}',
    ])

    result = validate_template_output(text)

    assert result.is_valid
    assert result.errors == []


def test_validate_template_output_rejects_non_object_json_line():
    result = validate_template_output('[{"character_name":"小夏"}]')

    assert not result.is_valid
    assert result.errors[0].line == 1
    assert "必须是 JSON 对象" in result.errors[0].message


def test_validate_template_output_requires_basic_fields():
    result = validate_template_output('{"character_name":"小夏","speech":"你好"}')

    assert not result.is_valid
    assert "缺少必填字段" in result.errors[0].message
    assert "sprite" in result.errors[0].message


def test_validate_template_output_reports_malformed_json_with_line_number():
    result = validate_template_output('{"character_name":"小夏",')

    assert not result.is_valid
    assert result.errors[0].line == 1
    assert "JSON 解析失败" in result.errors[0].message


def test_validate_template_output_checks_choice_option_count():
    one = validate_template_output('{"character_name":"CHOICE","speech":"只有一个","sprite":"-1"}')
    five = validate_template_output('{"character_name":"CHOICE","speech":"一/二/三/四/五","sprite":"-1"}')

    assert not one.is_valid
    assert "2-4 个选项" in one.errors[0].message
    assert not five.is_valid
    assert "2-4 个选项" in five.errors[0].message


def test_validate_template_output_warns_when_cg_prompt_is_probably_in_sprite():
    result = validate_template_output('{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}')

    assert result.is_valid
    assert result.warnings[0].line == 1
    assert "CG 的 prompt 应放在 speech" in result.warnings[0].message


def test_validate_template_output_warns_unknown_uppercase_control_token():
    result = validate_template_output('{"character_name":"FOO","speech":"test","sprite":"-1"}')

    assert result.is_valid
    assert "未知控制 token" in result.warnings[0].message


def test_validate_template_output_allows_normal_character_name():
    result = validate_template_output('{"character_name":"小夏","speech":"你好","sprite":"0"}')

    assert result.is_valid
    assert result.warnings == []
