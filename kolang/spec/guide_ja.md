## kolang ガイド

kolang は 構文可変なスモール言語です。

### 値とリテラル

```pylike
n = 42                 # 数（符号なしの整数）
pi = 3.14              # 小数
s1 = "こんにちは"      # 文字列（"..." と '...' が使える）
s2 = 'it works'
yes = True
no = False
nothing = None
minus = -7             # 符号の反転は neg（Num は非負）
xs = [1, 2, 3]
empty = []
nested = [[1, 2], [3, 4]]
words = ["a", "b"]
```

### 名前

英数字と _ は、そのまま名前にできる（先頭は英字、_ は途中だけ）。

```pylike
snake_case = 1
```

### 代入・添字

```pylike
first = xs[0]
cell = nested[1][0]          # 添字は重ねられる
xs[1] = 20                   # 要素への代入
nested[0][1] = 99
```


### 増やす・減らす・追加

```pylike
count = 0
count += 1                   # += 1 だけ（増やす）
count -= 1                   # -= 1 だけ（減らす）

xs = [1, 2, 3]
xs.append(4)
```

### 条件分岐

比較は 6 種類。条件分岐内だけに比較は書ける
else if はないので、入れ子にする

```pylike
if n == 42:
    print("eq")
if n != 0:
    print("ne")
if n < 100:
    print("lt")
if n > 1:
    print("gt")
if n <= 42:
    print("le")
if n >= 42:
    print("ge")

if n < 10:
    print("small")
else:
    if n < 100:
        print("medium")
    else:
        print("large")
```

### n 回くり返す

```pylike
for _ in range(3):
    count += 1
for _ in range(len(xs)):
    count += 1

# --- 条件つきの無限ループの代わり
i = 0
for _ in range(1000):
    if i == 5:
        break
    i += 1
```

### 関数定義・return・呼び出し

```pylike
def double(x):
    return mul(x, 2)

def greet(name):
    print(add("hello, ", name))      # return のない関数は None を返す

def sum_to(limit):
    total = 0
    k = 0
    for _ in range(limit):
        k += 1
        total = add(total, k)
    return total

def first_negative(ys):
    # return は、くり返しの中からも関数を抜ける
    j = 0
    for _ in range(len(ys)):
        if ys[j] < 0:
            return ys[j]
        j += 1
    return None

def add_pair(a, b):                  # 引数は複数
    return add(a, b)

def no_args():                       # 引数なし
    return 1

# 関数の中で別の関数を呼ぶ・再帰する
def fact(m):
    if m <= 1:
        return 1
    return mul(m, fact(sub(m, 1)))

# --- 呼び出しは式としても、文（戻り値は捨てる）としても書ける ---
greet("kolang")
print(double(21))
print(sum_to(10))
print(first_negative([3, 1, -4, 1]))
print(add_pair(add_pair(1, 2), double(3)))     # 引数に呼び出しを入れ子にする
print(no_args())
print(fact(5))
```

### サンプル

#### 逆順のリストを作る

```pylike
def reverse(xs):
    r = []
    i = len(xs)
    for _ in range(len(xs)):
        i -= 1
        r.append(xs[i])
    return r
```

#### 偶数だけを集める（filter）

```pylike
def evens(xs):
    r = []
    i = 0
    for _ in range(len(xs)):
        if mod(xs[i], 2) == 0:
            r.append(xs[i])
        i += 1
    return r
```

#### 最大値の位置を返す（見つからなければ -1）

```pylike
def argmax(xs):
    best = -1
    i = 0
    for _ in range(len(xs)):
        if best < 0:
            best = i
        else:
            if xs[i] > xs[best]:
                best = i
        i += 1
    return best
```

#### 文字列を 1 文字ずつ見て、母音を数える

```pylike
def count_vowels(s):
    vowels = "aeiou"
    c = 0
    i = 0
    for _ in range(len(s)):
        j = 0
        for _ in range(len(vowels)):
            if s[i] == vowels[j]:
                c += 1
            j += 1
        i += 1
    return c
```

#### バブルソート（添字への代入で、その場で入れ替える）

```pylike
def bubble_sort(xs):
    n = len(xs)
    for _ in range(n):
        i = 0
        for _ in range(sub(n, 1)):
            if xs[i] > xs[add(i, 1)]:
                t = xs[i]
                xs[i] = xs[add(i, 1)]
                xs[add(i, 1)] = t
            i += 1
    return xs
```

#### 素数判定（break で早く抜ける）

```pylike
def is_prime(n):
    if n < 2:
        return False
    d = 1
    for _ in range(n):
        d += 1
        if d >= n:
            break
        if mod(n, d) == 0:
            return False
    return True
```