"""`.ko` ファイル: 1 行目でシンタックスを指定し、コードを ``` で囲む。

    ```jalike:jslike(assign)
    ...コード...
    ```

1 行目の ``` の後ろがシンタックス（名前、JSON のパス、カスケード）。
閉じの ``` の行までがコードで、その後ろは読まない。
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

EXTENSION = ".ko"
FENCE = "```"


class KoFileError(ValueError):
    pass


def split_ko(text: str) -> Tuple[str, str]:
    """`.ko` の中身を（シンタックスの指定, コード）に分ける。"""
    lines = text.lstrip("﻿").splitlines()
    if not lines or not lines[0].startswith(FENCE):
        raise KoFileError("1 行目は ```シンタックス（例: ```jalike:jslike(assign)）で始めてください")
    spec = lines[0][len(FENCE):].strip()
    if not spec:
        raise KoFileError("1 行目の ``` の後ろにシンタックスを書いてください")
    body = []
    for line in lines[1:]:
        if line.strip() == FENCE:
            return spec, "".join(l + "\n" for l in body)
        body.append(line)
    raise KoFileError("閉じの ``` がありません")


def map_blocks(text: str, fn: Callable[[str, str], Optional[Tuple[str, str]]]) -> Tuple[str, int]:
    """文書の中の ```シンタックス 〜 ``` のブロックを全部、fn(spec, code) -> (新しい spec, 新しいコード) で書き換える。

    fn が None を返したブロックと、ブロックの外の文章は、そのまま残す。
    info string のない ``` のブロックは対象外。（書き換えた後の文書, 書き換えたブロックの数）。
    """
    out, count = [], 0
    lines = text.lstrip("﻿").splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith(FENCE):
            out.append(line)
            i += 1
            continue
        spec = line[len(FENCE):].strip()
        j = i + 1
        while j < len(lines) and lines[j].strip() != FENCE:
            j += 1
        if j >= len(lines):
            raise KoFileError(f"{i + 1} 行目: 閉じの ``` がありません")
        body = "".join(lines[i + 1:j])
        result = fn(spec, body) if spec else None
        if result is None:
            out.extend(lines[i:j + 1])
        else:
            new_spec, new_code = result
            out.append(f"{FENCE}{new_spec}\n{new_code.rstrip(chr(10))}\n{lines[j].strip()}\n")
            count += 1
        i = j + 1
    return "".join(out), count


def join_ko(spec: str, code: str) -> str:
    """コードを `.ko` の形に包む。"""
    return f"{FENCE}{spec}\n{code.rstrip(chr(10))}\n{FENCE}\n"


def is_ko(path) -> bool:
    return path is not None and str(path).endswith(EXTENSION)
