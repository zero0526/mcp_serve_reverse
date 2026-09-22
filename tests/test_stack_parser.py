from app.adapters.graph.stack_parser import parse_v8_stack


def test_parse_v8_stack_standard_frames():
    stack = """Error
    at calculateHash (http://localhost:3000/app.js:45:12)
    at submitOrderData (http://localhost:3000/app.js:80:5)
    at http://localhost:3000/main.js:100:20"""

    frames = parse_v8_stack(stack)
    assert len(frames) == 3
    assert frames[0].function_name == "calculateHash"
    assert frames[0].file_url == "http://localhost:3000/app.js"
    assert frames[0].line_no == 45
    assert frames[0].col_no == 12

    assert frames[1].function_name == "submitOrderData"
    assert frames[1].line_no == 80

    assert frames[2].function_name == "<anonymous>"
    assert frames[2].file_url == "http://localhost:3000/main.js"
    assert frames[2].line_no == 100


def test_parse_v8_stack_eval_and_async_frames():
    stack = """Error
    at window.fetch (<anonymous>:173:19)
    at submitOrderData (eval at evaluate (:311:30), <anonymous>:13:40)
    at async eval (eval at evaluate (:311:30), <anonymous>:33:13)
    at async <anonymous>:337:30"""

    frames = parse_v8_stack(stack)
    # window.fetch is filtered out as internal keyword
    assert len(frames) == 3
    assert frames[0].function_name == "submitOrderData"
    assert frames[0].file_url == "<anonymous>"
    assert frames[0].line_no == 13
    assert frames[0].col_no == 40

    assert frames[1].function_name == "eval"
    assert frames[1].line_no == 33

    assert frames[2].function_name == "<anonymous>"
    assert frames[2].line_no == 337


def test_parse_v8_stack_filters_internal_instrumentation():
    stack = """Error
    at Response.json (<anonymous>:320:28)
    at Object.get (<anonymous>:290:31)
    at window.__api_lineage_emit__ (<anonymous>:14:22)
    at BindingsController.callBinding (<anonymous>:308:48)
    at handleResponseCallback (eval at evaluate (:311:30), <anonymous>:28:51)"""

    frames = parse_v8_stack(stack)
    assert len(frames) == 1
    assert frames[0].function_name == "handleResponseCallback"
    assert frames[0].line_no == 28


def test_parse_v8_stack_empty():
    assert parse_v8_stack(None) == []
    assert parse_v8_stack("") == []
    assert parse_v8_stack("No frames here") == []
