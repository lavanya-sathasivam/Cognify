"""Reference solution for PY-C7-BANK-ACCOUNT-TRANSFER (Shopping Cart Totals).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


class ShoppingCart:
    """One cart with its own item count."""

    def __init__(self, name):
        self.name = name
        self.count = 0

    def add(self, qty):
        self.count += qty


def main():
    import sys
    lines = sys.stdin.read().strip().splitlines()
    if not lines:
        return
    m = int(lines[0].split()[0])
    carts = {}
    out = []
    for line in lines[1:1 + m]:
        parts = line.split()
        if parts[0] == "ADD":
            if parts[1] not in carts:
                carts[parts[1]] = ShoppingCart(parts[1])
            carts[parts[1]].add(int(parts[2]))
        elif parts[0] == "TOTAL":
            if parts[1] in carts:
                out.append(str(carts[parts[1]].count))
            else:
                out.append("UNKNOWN")
    sys.stdout.write("\n".join(out))


if __name__ == "__main__":
    main()
