from counter import count_items


def test_empty():
    assert count_items([]) == 0


def test_one():
    assert count_items(["a"]) == 1


def test_many():
    assert count_items([1, 2, 3]) == 3
