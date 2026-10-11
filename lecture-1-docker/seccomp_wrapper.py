#!/usr/bin/env python3
import errno
import os
import sys

import pyseccomp

DENY = ["mkdir", "mkdirat", "settimeofday", "clock_settime", "reboot", "kexec_load"]

f = pyseccomp.SyscallFilter(defaction=pyseccomp.ALLOW)
for name in DENY:
    try:
        f.add_rule(pyseccomp.ERRNO(errno.EPERM), name)
    except RuntimeError:
        pass
f.load()

os.execvp(sys.argv[1], sys.argv[1:])