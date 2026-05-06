"""
Kill process listening on a TCP port (Windows-friendly).

Usage:
  python tools/kill_port.py 8000
"""
import re
import subprocess
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/kill_port.py <port>")
        return 2

    port = sys.argv[1].strip()
    if not port.isdigit():
        print(f"[FAIL] Invalid port: {port!r}")
        return 2

    # netstat output example:
    #   TCP    127.0.0.1:8000   0.0.0.0:0   LISTENING   12345
    cmd = ["cmd", "/c", "netstat -ano -p tcp"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print("[FAIL] netstat failed")
        print(p.stdout)
        print(p.stderr)
        return 1

    pid_set = set()
    for line in p.stdout.splitlines():
        # Normalize whitespace and split; typical fields: Proto, Local Address, Foreign Address, State, PID
        parts = line.split()
        if len(parts) < 5:
            continue
        proto, local_addr, _foreign_addr, state, pid = parts[0], parts[1], parts[2], parts[3], parts[4]
        if proto.upper() != "TCP":
            continue
        if state.upper() != "LISTENING":
            continue
        if not local_addr.endswith(f":{port}"):
            continue
        if pid.isdigit():
            pid_set.add(pid)

    if not pid_set:
        print(f"[OK] No LISTENING process found on port {port}")
        return 0

    for pid in sorted(pid_set):
        print(f"[INFO] Killing PID {pid} on port {port}")
        k = subprocess.run(["cmd", "/c", f"taskkill /F /PID {pid}"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(k.stdout.strip())
        if k.returncode != 0:
            print(k.stderr.strip())
            return 1

    print("[OK] Killed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

