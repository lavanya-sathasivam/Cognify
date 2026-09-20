"""Reference solution for PY-C6-COUNT-WORD (Count Word Occurrences).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def count_word(words, query):
    """Return how many times query appears in words."""
    counts = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return counts.get(query, 0)


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    n = int(data[0])
    words = data[1:1 + n]
    query = data[1 + n]
    print(count_word(words, query))


if __name__ == "__main__":
    main()
