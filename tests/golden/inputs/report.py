def summary(rows):
    count = 0
    best = None
    for row in rows:
        if row.value is None:
            continue
        count = count + 1
        if best is None or row.value > best:
            best = row.value
    print("count", count)
    print("best", best)
    return count, best


def unrelated(path):
    handle = open(path)
    text = handle.read()
    handle.close()
    words = text.split()
    return len(words)
