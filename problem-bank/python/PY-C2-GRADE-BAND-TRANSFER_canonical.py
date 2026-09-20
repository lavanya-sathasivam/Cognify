"""Reference solution for PY-C2-GRADE-BAND-TRANSFER (Parcel Shipping Class).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def shipping_class(w):
    """Return FREIGHT, STANDARD, LIGHT, or INVALID for weight w."""
    if w >= 50:
        return "FREIGHT"
    if w >= 10:
        return "STANDARD"
    if w >= 1:
        return "LIGHT"
    return "INVALID"


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    w = int(data[0])
    print(shipping_class(w))


if __name__ == "__main__":
    main()
