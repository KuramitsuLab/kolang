## kolang Guide (3 examples)

kolang is a small language with variable syntax.
The following 3 functions show how to write it.

### Integer arithmetic (greatest common divisor)

```pylike
def gcd(a, b):
    for _ in range(1000):
        if b == 0:
            break
        t = mod(a, b)
        a = b
        b = t
    return a
```

### String processing (count vowels)

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

### List processing (build a reversed list)

```pylike
def reverse(xs):
    r = []
    i = len(xs)
    for _ in range(len(xs)):
        i -= 1
        r.append(xs[i])
    return r
```
