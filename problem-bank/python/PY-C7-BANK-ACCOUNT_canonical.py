"""Reference solution for PY-C7-BANK-ACCOUNT (Bank Account Ledger).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


class BankAccount:
    """One account with its own balance."""

    def __init__(self, name, balance):
        self.name = name
        self.balance = balance

    def deposit(self, amt):
        self.balance += amt


def main():
    import sys
    lines = sys.stdin.read().strip().splitlines()
    if not lines:
        return
    m = int(lines[0].split()[0])
    accounts = {}
    out = []
    for line in lines[1:1 + m]:
        parts = line.split()
        if parts[0] == "OPEN":
            accounts[parts[1]] = BankAccount(parts[1], int(parts[2]))
        elif parts[0] == "DEPOSIT":
            if parts[1] in accounts:
                accounts[parts[1]].deposit(int(parts[2]))
        elif parts[0] == "BALANCE":
            if parts[1] in accounts:
                out.append(str(accounts[parts[1]].balance))
            else:
                out.append("UNKNOWN")
    sys.stdout.write("\n".join(out))


if __name__ == "__main__":
    main()
