from skill_token_bench.agents.claude_code import parse_usage_blob


def test_parse_nested_usage():
    blob = '{"result":"hi","usage":{"input_tokens":100,"output_tokens":20,"cache_read_input_tokens":5}}'
    usage = parse_usage_blob(blob)
    assert usage is not None
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.cache_read_tokens == 5


def test_parse_ndjson():
    blob = "log line\n{\"usage\":{\"prompt_tokens\":10,\"completion_tokens\":3}}\n"
    usage = parse_usage_blob(blob)
    assert usage is not None
    assert usage.input_tokens == 10
    assert usage.output_tokens == 3
