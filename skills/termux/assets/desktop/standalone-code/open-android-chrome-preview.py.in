#!/usr/bin/python3
"""Route the isolated profile's local HTTP previews to Android Chrome."""
import os
import sys
from urllib.parse import urlsplit

uri = sys.argv[1]
url = urlsplit(uri)
if url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1"):
    app = @AM@
    env = os.environ.copy()
    for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT", "CLASSPATH"):
        env.pop(name, None)
    os.execve(app, [app, "start", "--user", "0", "-a", "android.intent.action.VIEW",
                    "-c", "android.intent.category.BROWSABLE", "-d", uri, "-p", "com.android.chrome"], env)

os.execv("/usr/bin/gio", ["/usr/bin/gio", "launch", @FALLBACK@, uri])
