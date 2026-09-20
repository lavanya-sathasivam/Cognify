"""Reference solution for PY-C5-LAST-ITEM (Last List Item).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def last_item(nums):
    """Return the last value in nums."""
    return nums[len(nums) - 1]


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    nums = list(map(int, data[1:1 + n]))
    print(last_item(nums))


if __name__ == "__main__":
    main()
