"""Reference solution for PY-C2-EITHER-OR (Either Or Check).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def either_or(x):
    """Return YES when x is 5 or 10, else NO."""
    if x == 5 or x == 10:
        return "YES"
    return "NO"


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    x = int(data[0])
    print(either_or(x))


if __name__ == "__main__":
    main()
