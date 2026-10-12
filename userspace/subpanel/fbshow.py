#!/usr/bin/env python3
"""Show a raw image on a DRM fbdev framebuffer, forcing a modeset first.

The DRM fbdev emulation only flushes to the panel once the pipe is enabled;
nothing enables fb1 (the sub-LCD) at boot, so plain writes never reach it.
FBIOPUT_VSCREENINFO with FB_ACTIVATE_FORCE makes drm_fb_helper do the modeset.

Usage: fbshow.py /dev/fb1 image.raw
"""
import fcntl, sys

FBIOGET_VSCREENINFO, FBIOPUT_VSCREENINFO = 0x4600, 0x4601
FB_ACTIVATE_NOW, FB_ACTIVATE_FORCE = 0, 128
ACTIVATE_OFF = 21 * 4  # fb_var_screeninfo.activate

with open(sys.argv[1], "r+b", buffering=0) as fb:
    var = bytearray(160)
    fcntl.ioctl(fb, FBIOGET_VSCREENINFO, var)
    var[ACTIVATE_OFF:ACTIVATE_OFF + 4] = (FB_ACTIVATE_NOW | FB_ACTIVATE_FORCE).to_bytes(4, "little")
    fcntl.ioctl(fb, FBIOPUT_VSCREENINFO, var)
    fb.write(open(sys.argv[2], "rb").read())
