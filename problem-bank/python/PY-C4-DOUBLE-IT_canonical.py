"""Reference solution for PY-C4-DOUBLE-IT (Double It Function).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def double_it(n):
    """Return 2 * n."""
    return 2 * n


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    print(double_it(n))


if __name__ == "__main__":
    main()
