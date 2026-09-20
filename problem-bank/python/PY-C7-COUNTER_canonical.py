"""Reference solution for PY-C7-COUNTER (Simple Counter Object).

DATA ONLY: this file documents the canonical solution for humans and for
test-data review. It is NEVER executed by the Cognify pipeline — student
code runs only inside the existing execution-service Docker sandbox
(services/execution-service), and problem-bank tests use the existing
FakeSandboxRunner so no host interpreter ever runs untrusted code.
"""


class Counter:
    """A counter starting at 0."""

    def __init__(self):
        self.value = 0

    def inc(self):
        self.value += 1

    def dec(self):
        self.value -= 1

    def show(self):
        return self.value


def main():
    import sys
    lines = sys.stdin.read().strip().splitlines()
    if not lines:
        return
    m = int(lines[0].split()[0])
    counter = Counter()
    out = []
    for line in lines[1:1 + m]:
        cmd = line.split()[0]
        if cmd == "INC":
            counter.inc()
        elif cmd == "DEC":
            counter.dec()
        elif cmd == "SHOW":
            out.append(str(counter.show()))
    sys.stdout.write("\n".join(out))


if __name__ == "__main__":
    main()
