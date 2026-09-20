"""Reference solution for PY-C6-SAFE-LOOKUP (Safe Price Lookup).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""

PRICES = {"apple": 5, "banana": 3}


def lookup_price(query):
    """Return the price of query, or 0 when it is not stocked."""
    return PRICES.get(query, 0)


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    print(lookup_price(data[0]))


if __name__ == "__main__":
    main()
