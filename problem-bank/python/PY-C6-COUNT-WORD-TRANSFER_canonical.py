"""Reference solution for PY-C6-COUNT-WORD-TRANSFER (Stock Totals).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def stock_total(records, query):
    """Return the summed qty for query across (item, qty) records."""
    totals = {}
    for item, qty in records:
        totals[item] = totals.get(item, 0) + qty
    return totals.get(query, 0)


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    records = []
    pos = 1
    for _ in range(n):
        records.append((data[pos], int(data[pos + 1])))
        pos += 2
    query = data[pos]
    print(stock_total(records, query))


if __name__ == "__main__":
    main()
