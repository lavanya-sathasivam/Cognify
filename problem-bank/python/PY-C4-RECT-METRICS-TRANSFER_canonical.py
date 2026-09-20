"""Reference solution for PY-C4-RECT-METRICS-TRANSFER (Box Volume and Surface).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


def volume_of(l, w, h):
    """Return the volume l * w * h."""
    return l * w * h


def surface_of(l, w, h):
    """Return the surface area 2 * (l*w + w*h + h*l)."""
    return 2 * (l * w + w * h + h * l)


def main():
    import sys
    data = sys.stdin.read().strip().split()
    if not data:
        return
    l = int(data[0])
    w = int(data[1])
    h = int(data[2])
    print(f"{volume_of(l, w, h)} {surface_of(l, w, h)}")


if __name__ == "__main__":
    main()
