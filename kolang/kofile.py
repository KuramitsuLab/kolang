"""`.ko` ファイル: 1 行目でシンタックスを指定し、コードを ``` で囲む。

    ```ja:jslike(assign)
    ...コード...
    ```

1 行目の ``` の後ろがシンタックス（名前、JSON のパス、カスケード）。
閉じの ``` の行までがコードで、その後ろは読まない。
"""

from __future__ import annotations

from typing import Tuple

EXTENSION = ".ko"
FENCE = "```"


class KoFileError(ValueError):
    pass


def split_ko(text: str) -> Tuple[str, str]:
    """`.ko` の中身を（シンタックスの指定, コード）に分ける。"""
    lines = text.lstrip("﻿").splitlines()
    if not lines or not lines[0].startswith(FENCE):
        raise KoFileError("1 行目は ```シンタックス（例: ```ja:jslike(assign)）で始めてください")
    spec = lines[0][len(FENCE):].strip()
    if not spec:
        raise KoFileError("1 行目の ``` の後ろにシンタックスを書いてください")
    body = []
    for line in lines[1:]:
        if line.strip() == FENCE:
            return spec, "".join(l + "\n" for l in body)
        body.append(line)
    raise KoFileError("閉じの ``` がありません")


def join_ko(spec: str, code: str) -> str:
    """コードを `.ko` の形に包む。"""
    return f"{FENCE}{spec}\n{code.rstrip(chr(10))}\n{FENCE}\n"


def is_ko(path) -> bool:
    return path is not None and str(path).endswith(EXTENSION)
