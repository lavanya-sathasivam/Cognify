"""Reference solution for PY-C1-TEMP-CONVERT (Fahrenheit to Celsius).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def fahrenheit_to_celsius(f):
    """Return the Celsius equivalent of Fahrenheit f, rounded to 1 decimal."""
    return (f - 32) * 5 / 9


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    f = int(data[0])
    print(f"{fahrenheit_to_celsius(f):.1f}")


if __name__ == "__main__":
    main()
