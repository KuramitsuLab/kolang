"""標準ライブラリ関数。

kolang には演算子も print もない。足し算や出力は、ここの関数で書く（add(1, 2)、print(x)）。
最初の実装は Python のもの。値は Python のオブジェクトなので、エラーの種類とメッセージも Python と同じ。

関数には **標準名**（このファイルのキー）がある。シンタックスの JSON の `stdlib` のキー（オブジェクト）で、
標準名 → そのシンタックスでの名前に変えられる（syntax.md）。

    "stdlib": {"print": "表示", "add": "足し算"}

関数を足す・変えるときは、make_stdlib() の表を直す。評価器は pyeval.py。
"""

from __future__ import annotations

import builtins
import operator
import sys
from typing import Callable

# Python の組み込み関数のうち、そのまま使うもの
PYTHON_BUILTINS = ("abs", "bool", "chr", "float", "input", "int", "len", "list", "max", "min",
                   "ord", "range", "repr", "reversed", "round", "sorted", "str", "sum")

# リストの長さを縮める操作。kolang の文は append（伸ばす）しか持たないので、kolang では書けない。
# `xs.pop()` を `pop(xs)` と書く（Python のメソッドをそのまま呼ぶ）。
# join / split / sort など、kolang で書けるものは lib/ に kolang で定義する（lib/NAME.ko）。
METHODS = ("pop", "remove", "clear")


def make_stdlib(stdout=None) -> dict[str, Callable]:
    """標準名 → 関数。print の出力先は stdout（None なら、呼ばれた時点の sys.stdout）。"""

    def print_(*args):
        print(*args, file=sys.stdout if stdout is None else stdout)

    table: dict[str, Callable] = {"print": print_}
    table.update({name: getattr(builtins, name) for name in PYTHON_BUILTINS})
    # 四則演算と、剰余・べき乗。Python の演算そのもの
    # （add は文字列・リストの連結にも使える、div は真の除算 /、mod は %、pow は **）
    table.update(add=operator.add, sub=operator.sub, mul=operator.mul, div=operator.truediv,
                 mod=operator.mod, pow=operator.pow)
    for name in METHODS:
        table[name] = _method(name)
    return table


def _method(name: str) -> Callable:
    def call(obj, *args):
        return getattr(obj, name)(*args)
    call.__name__ = name
    return call


NAMES: tuple = tuple(make_stdlib())


def local_names(overrides: dict) -> dict[str, str]:
    """標準名 → シンタックスでの名前（overrides にないものは標準名のまま）。"""
    return {name: overrides.get(name, name) for name in NAMES}
