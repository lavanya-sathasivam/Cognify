"""Reference solution for PY-C5-FIND-MAX-TRANSFER (Longest Word).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def longest_word(words):
    """Return the longest word (first one on ties)."""
    best = words[0]
    for i in range(1, len(words)):
        if len(words[i]) > len(best):
            best = words[i]
    return best


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    words = data[1:1 + n]
    print(longest_word(words))


if __name__ == "__main__":
    main()
