def count_items(items: list) -> int:
    """Return number of items. Intentionally buggy for the benchmark."""
    total = 0
    for i in range(1, len(items)):  # off-by-one: skips index 0
        total += 1
    return total
