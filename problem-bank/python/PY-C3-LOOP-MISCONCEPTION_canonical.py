"""Reference solution for PY-C3-LOOP-MISCONCEPTION (Sum One to N).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and Step 12/13 tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.

Note the inclusive upper bound (``n + 1``): the C3-M05 mistake this probe
targets is writing ``range(1, n)``, which drops the final value (and
yields 0 for n = 1 instead of 1).
"""


def sum_to_n(n):
    """Return the sum 1 + 2 + ... + n inclusive."""
    total = 0
    for i in range(1, n + 1):
        total += i
    return total


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    print(sum_to_n(n))


if __name__ == "__main__":
    main()
