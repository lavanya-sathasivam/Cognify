"""Reference solution for PY-C8-FACTORIAL (Recursive Factorial).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def factorial(n):
    """Return n! recursively."""
    if n == 0:
        return 1
    return n * factorial(n - 1)


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    print(factorial(n))


if __name__ == "__main__":
    main()
