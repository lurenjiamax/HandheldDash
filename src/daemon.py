#!/usr/bin/python
# SPDX-License-Identifier: LGPL-3.0-or-later
"""HandheldDash hardware service entrypoint."""
import sys
sys.path.append('/usr/lib/aynthor')
from handhelddash.services.application import main

if __name__=='__main__':
    main()
