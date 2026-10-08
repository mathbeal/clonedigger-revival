# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

# Input of tests/test_syntax.py: every recent construct, written twice under other
# names, so that each can be read and found as a clone. Not meant to run.

import asyncio


def gen_a(items):
    total = 0
    for item in items:
        value = yield item * 2
        if value:
            total += value
    yield from range(total)
    return total


def gen_b(rows):
    acc = 0
    for row in rows:
        got = yield row * 2
        if got:
            acc += got
    yield from range(acc)
    return acc


def match_a(command):
    match command:
        case {"action": "move", "x": x, "y": y} if x > 0:
            result = (x, y)
            log = f"moved {x=} to {y!r:>5}"
        case [first, *rest]:
            result = first
            log = "list"
        case Point(x=0) | Point(y=0):
            result = None
            log = "axis"
        case _:
            result = None
            log = "other"
    return result, log


def match_b(order):
    match order:
        case {"action": "move", "x": a, "y": b} if a > 0:
            out = (a, b)
            msg = f"moved {a=} to {b!r:>5}"
        case [head, *tail]:
            out = head
            msg = "list"
        case Point(x=0) | Point(y=0):
            out = None
            msg = "axis"
        case _:
            out = None
            msg = "other"
    return out, msg


async def fetch_a(session, urls):
    async with session as client:
        async for url in client.stream(urls):
            if (size := len(url)) > 10:
                await asyncio.sleep(size)
    try:
        await client.close()
    except* (ValueError, TypeError) as group:
        print(group)


async def fetch_b(conn, links):
    async with conn as c:
        async for link in c.stream(links):
            if (n := len(link)) > 10:
                await asyncio.sleep(n)
    try:
        await c.close()
    except* (ValueError, TypeError) as errors:
        print(errors)


type Pair[T] = tuple[T, T]


class Box[T]:
    def first[U: int](self, value: U) -> U:
        lam = lambda a, /, b=1, *c, d, **e: (a, b, c, d, e)
        data = [n for n in range(3) if n] + [*{1, 2}] + list({k: v for k, v in {}.items()})
        return value
