"""Reference solution for PY-C3-COUNT-DIV-TRANSFER (Count Cold Days).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and Step 12/13 tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def count_cold_days(temps, threshold):
    """Return how many temperatures in temps are strictly below threshold."""
    count = 0
    for t in temps:
        if t < threshold:
            count += 1
    return count


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    threshold = int(data[1])
    temps = list(map(int, data[2:2 + n]))
    print(count_cold_days(temps, threshold))


if __name__ == "__main__":
    main()
