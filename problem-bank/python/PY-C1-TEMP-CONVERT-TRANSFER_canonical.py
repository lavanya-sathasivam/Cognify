"""Reference solution for PY-C1-TEMP-CONVERT-TRANSFER (Hours From Minutes).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def hours_from_minutes(m):
    """Return the hours equivalent of m minutes as a float."""
    return m / 60


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    m = int(data[0])
    print(f"{hours_from_minutes(m):.1f}")


if __name__ == "__main__":
    main()
