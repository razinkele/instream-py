"""v0.46 Task A5: undo/redo stack semantics.

Pure unit test of the snapshot stacking logic — exercises the list
mutation / cap-at-10 behaviour without a Shiny session.
"""
def _push_undo(stack: list, snap: dict, cap: int = 10) -> list:
    stack = list(stack)
    stack.append(snap)
    if len(stack) > cap:
        stack = stack[-cap:]
    return stack


def test_push_undo_caps_at_ten():
    stack = []
    for i in range(15):
        stack = _push_undo(stack, {"i": i})
    assert len(stack) == 10
    assert stack[0]["i"] == 5
    assert stack[-1]["i"] == 14


def test_push_undo_preserves_order_under_cap():
    stack = []
    for i in range(5):
        stack = _push_undo(stack, {"i": i})
    assert [s["i"] for s in stack] == [0, 1, 2, 3, 4]


def test_undo_pop_then_redo_restores_state():
    undo_stack = [{"i": 1}, {"i": 2}, {"i": 3}]
    redo_stack = []
    current = {"i": 4}

    snap = undo_stack.pop()
    redo_stack.append(current)
    current = snap
    assert current == {"i": 3}
    assert undo_stack == [{"i": 1}, {"i": 2}]
    assert redo_stack == [{"i": 4}]

    snap = redo_stack.pop()
    undo_stack.append(current)
    current = snap
    assert current == {"i": 4}
    assert undo_stack == [{"i": 1}, {"i": 2}, {"i": 3}]
    assert redo_stack == []
