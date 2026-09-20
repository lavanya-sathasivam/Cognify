"""Reference solution for PY-C4-RECT-METRICS (Rectangle Area and Perimeter).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def area_of(w, h):
    """Return the area w * h."""
    return w * h


def perimeter_of(w, h):
    """Return the perimeter 2 * (w + h)."""
    return 2 * (w + h)


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    w = int(data[0])
    h = int(data[1])
    print(f"{area_of(w, h)} {perimeter_of(w, h)}")


if __name__ == "__main__":
    main()
