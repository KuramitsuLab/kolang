## kolang Guide (10 examples)

kolang is a small language with variable syntax.
The following 10 functions show how to write it.

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

### String parsing (evaluate an expression like "1+1")

```pylike
def calc(s):
    total = 0
    num = 0
    sign = 1
    i = 0
    for _ in range(len(s)):
        ch = s[i]
        if ch == "+":
            total = add(total, mul(sign, num))
            num = 0
            sign = 1
        else:
            if ch == "-":
                total = add(total, mul(sign, num))
                num = 0
                sign = -1
            else:
                num = add(mul(num, 10), int(ch))
        i += 1
    return add(total, mul(sign, num))
```

### Loops with a changing condition (Collatz steps)

```pylike
def collatz_steps(n):
    steps = 0
    for _ in range(1000000):
        if n == 1:
            break
        if mod(n, 2) == 0:
            n = int(div(n, 2))
        else:
            n = add(mul(n, 3), 1)
        steps += 1
    return steps
```

### Sorting (bubble sort)

```pylike
def bubble_sort(xs):
    r = list(xs)
    n = len(r)
    for _ in range(n):
        i = 0
        for _ in range(sub(n, 1)):
            if r[i] > r[add(i, 1)]:
                t = r[i]
                r[i] = r[add(i, 1)]
                r[add(i, 1)] = t
            i += 1
    return r
```

### Numbers and strings (convert an integer to a string and reverse it)

```pylike
def reverse_digits(n):
    s = str(n)
    r = ""
    i = len(s)
    for _ in range(len(s)):
        i -= 1
        r = add(r, s[i])
    return r
```

### Repeated digit sums (soul number)

```pylike
def soul_number(n):
    for _ in range(1000):
        if n < 10:
            break
        s = 0
        for _ in range(len(str(n))):
            s = add(s, mod(n, 10))
            n = int(div(n, 10))
        n = s
    return n
```
