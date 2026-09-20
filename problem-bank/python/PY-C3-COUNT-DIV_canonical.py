"""Reference solution for PY-C3-COUNT-DIV (Count Divisible Numbers).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and Step 12 tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def count_divisible(nums, k):
    """Return how many numbers in nums are divisible by k."""
    count = 0
    for x in nums:
        if x % k == 0:
            count += 1
    return count


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    k = int(data[1])
    nums = list(map(int, data[2:2 + n]))
    print(count_divisible(nums, k))


if __name__ == "__main__":
    main()
