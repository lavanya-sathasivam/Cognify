"""Reference solution for PY-C5-FIND-MAX (Find the Maximum).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def find_max(nums):
    """Return the largest value in nums."""
    best = nums[0]
    for i in range(1, len(nums)):
        if nums[i] > best:
            best = nums[i]
    return best


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    nums = list(map(int, data[1:1 + n]))
    print(find_max(nums))


if __name__ == "__main__":
    main()
