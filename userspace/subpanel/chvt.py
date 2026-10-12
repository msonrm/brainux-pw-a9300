#!/usr/bin/env python3
"""chvt without the kbd package: switch the active virtual terminal (root)."""
import fcntl, sys

VT_ACTIVATE, VT_WAITACTIVE = 0x5606, 0x5607
n = int(sys.argv[1])
with open("/dev/tty0", "wb") as tty:
    fcntl.ioctl(tty, VT_ACTIVATE, n)
    fcntl.ioctl(tty, VT_WAITACTIVE, n)
