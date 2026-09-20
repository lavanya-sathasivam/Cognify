"""Reference solution for PY-C2-GRADE-BAND (Grade Band Classifier).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def grade_band(score):
    """Return DISTINCTION, MERIT, PASS, or FAIL for score."""
    if score >= 85:
        return "DISTINCTION"
    if score >= 65:
        return "MERIT"
    if score >= 50:
        return "PASS"
    return "FAIL"


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    score = int(data[0])
    print(grade_band(score))


if __name__ == "__main__":
    main()
