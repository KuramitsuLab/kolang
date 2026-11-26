## kolang Guide

kolang is a small language with variable syntax.

### Values and Literals

```pylike
n = 42                 # number (unsigned integer)
pi = 3.14              # decimal
s1 = "hello"           # string (both "..." and '...' can be used)
s2 = 'it works'
yes = True
no = False
nothing = None
minus = -7             # sign inversion is neg (Num is non-negative)
xs = [1, 2, 3]
empty = []
nested = [[1, 2], [3, 4]]
words = ["a", "b"]
```

### Names

Alphanumerics and _ can be used as-is in names (the first character must be a letter; _ is allowed only in the middle).

```pylike
snake_case = 1
```

### Assignment and Indexing

```pylike
first = xs[0]
cell = nested[1][0]          # indexes can be chained
xs[1] = 20                   # assignment to an element
nested[0][1] = 99
```


### Increment, Decrement, and Append

```pylike
count = 0
count += 1                   # only += 1 (increment)
count -= 1                   # only -= 1 (decrement)

xs = [1, 2, 3]
xs.append(4)
```

### Conditionals

There are 6 kinds of comparison. Comparisons can be written only inside a conditional.
There is no else if, so nest instead.

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

### Repeating n Times

```pylike
for _ in range(3):
    count += 1
for _ in range(len(xs)):
    count += 1

# --- instead of an infinite loop with a condition
i = 0
for _ in range(1000):
    if i == 5:
        break
    i += 1
```

### Function Definition, return, and Calls

```pylike
def double(x):
    return mul(x, 2)

def greet(name):
    print(add("hello, ", name))      # a function without return returns None

def sum_to(limit):
    total = 0
    k = 0
    for _ in range(limit):
        k += 1
        total = add(total, k)
    return total

def first_negative(ys):
    # return exits the function even from inside a loop
    j = 0
    for _ in range(len(ys)):
        if ys[j] < 0:
            return ys[j]
        j += 1
    return None

def add_pair(a, b):                  # multiple parameters
    return add(a, b)

def no_args():                       # no parameters
    return 1

# calling another function inside a function, and recursion
def fact(m):
    if m <= 1:
        return 1
    return mul(m, fact(sub(m, 1)))

# --- a call can be written as an expression or as a statement (the return value is discarded) ---
greet("kolang")
print(double(21))
print(sum_to(10))
print(first_negative([3, 1, -4, 1]))
print(add_pair(add_pair(1, 2), double(3)))     # calls nested as arguments
print(no_args())
print(fact(5))
```

### Samples

#### Build a Reversed List

```pylike
def reverse(xs):
    r = []
    i = len(xs)
    for _ in range(len(xs)):
        i -= 1
        r.append(xs[i])
    return r
```

#### Collect Only the Even Numbers (filter)

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

#### Return the Position of the Maximum (-1 if Not Found)

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

#### Look at a String One Character at a Time and Count Vowels

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

#### Bubble Sort (Swap in Place by Assigning to Indexes)

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

#### Primality Test (Exit Early with break)

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
