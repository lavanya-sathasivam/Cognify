"""Reference solution for PY-C8-FACTORIAL-TRANSFER (Recursive Integer Power).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def power(a, b):
    """Return a**b recursively."""
    if b == 0:
        return 1
    return a * power(a, b - 1)


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    a = int(data[0])
    b = int(data[1])
    print(power(a, b))


if __name__ == "__main__":
    main()
