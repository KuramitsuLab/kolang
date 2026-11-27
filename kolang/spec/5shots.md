## kolang Guide (5 examples)

kolang is a small language with variable syntax.
The following 5 functions show how to write it.

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

### Loops and conditions (FizzBuzz)

```pylike
def fizzbuzz(n):
    i = 0
    for _ in range(n):
        i += 1
        if mod(i, 15) == 0:
            print("FizzBuzz")
        else:
            if mod(i, 3) == 0:
                print("Fizz")
            else:
                if mod(i, 5) == 0:
                    print("Buzz")
                else:
                    print(i)
```

### Decimal arithmetic (area of a circle)

```pylike
def circle_area(r):
    pi = 3.14159
    return round(mul(pi, mul(r, r)), 2)
```
