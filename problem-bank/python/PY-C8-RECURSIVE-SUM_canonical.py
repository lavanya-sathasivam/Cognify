"""Reference solution for PY-C8-RECURSIVE-SUM (Recursive Sum to N).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def recursive_sum(n):
    """Return 1 + 2 + ... + n recursively."""
    if n == 1:
        return 1
    return n + recursive_sum(n - 1)


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    print(recursive_sum(n))


if __name__ == "__main__":
    main()
