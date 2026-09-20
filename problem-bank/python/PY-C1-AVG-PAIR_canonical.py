"""Reference solution for PY-C1-AVG-PAIR (Average of Two Numbers).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def average_pair(a, b):
    """Return the average of a and b as a float."""
    return (a + b) / 2


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    a = int(data[0])
    b = int(data[1])
    print(f"{average_pair(a, b):.1f}")


if __name__ == "__main__":
    main()
