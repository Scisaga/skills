#!/usr/bin/env python3
"""Install the SCM split-button touch fix in a standalone VS Code workbench."""
from collections import deque
import json
import os
import select
import sys
import time
from urllib.parse import urlsplit

WORKBENCH = "/usr/share/code/resources/app/out/vs/code/electron-browser/workbench/workbench.html"
TOUCH_FIX = """
(() => {
    if (window !== window.top || location.protocol !== "vscode-file:" ||
        location.host !== "vscode-app" ||
        location.pathname !== "/usr/share/code/resources/app/out/vs/code/electron-browser/workbench/workbench.html") {
        return false;
    }
    const installed = Symbol.for("scisaga.tablet-vscode.scm-touch-menu");
    if (window[installed]) {
        return true;
    }
    window[installed] = true;
    const selector = ".scm-view .monaco-button-dropdown .monaco-dropdown-button[aria-haspopup=true]";
    window.addEventListener("-monaco-gesturetap", event => {
        const arrow = event.target instanceof Element && event.target.closest(selector);
        if (!arrow || arrow.getAttribute("aria-disabled") === "true") {
            return;
        }
        const wasExpanded = arrow.getAttribute("aria-expanded") === "true";
        event.stopImmediatePropagation();
        if (wasExpanded) {
            return;
        }
        // The enclosing list handles the same touch and takes focus. Open the menu after that dispatch.
        setTimeout(() => {
            if (arrow.isConnected && arrow.getAttribute("aria-expanded") === "false" &&
                arrow.getAttribute("aria-disabled") !== "true") {
                arrow.click();
            }
        }, 0);
    }, true);
    return true;
})();
"""


def is_workbench(target):
    if target.get("type") != "page":
        return False
    url = urlsplit(target.get("url", ""))
    return url.scheme == "vscode-file" and url.netloc == "vscode-app" and url.path == WORKBENCH



class ProtocolError(RuntimeError):
    pass


class PrivatePipe:
    """Read and write the NUL-terminated messages on Electron's inherited pipes."""

    def __init__(self):
        self.buffer = b""
        self.request_id = 0
        self.events = deque()

    def receive(self, deadline=None):
        while b"\0" not in self.buffer:
            if deadline is not None and not select.select([0], [], [], max(0, deadline - time.monotonic()))[0]:
                raise TimeoutError("No response on the private DevTools pipe")
            data = os.read(0, 65536)
            if not data:
                raise EOFError
            self.buffer += data
        message, _, self.buffer = self.buffer.partition(b"\0")
        return json.loads(message)

    def request(self, method, params, session=None):
        self.request_id += 1
        message = {"id": self.request_id, "method": method, "params": params}
        if session:
            message["sessionId"] = session
        sys.stdout.buffer.write(json.dumps(message).encode() + b"\0")
        sys.stdout.buffer.flush()
        deadline = time.monotonic() + 5
        while True:
            response = self.receive(deadline)
            if response.get("id") == self.request_id:
                if "error" in response:
                    raise ProtocolError(f"{method}: {response['error']['message']}")
                return response["result"]
            if "method" in response:
                self.events.append(response)

    def event(self):
        while True:
            message = self.events.popleft() if self.events else self.receive()
            if "method" in message:
                return message


def evaluate(pipe, session):
    for _ in range(12):
        try:
            result = pipe.request("Runtime.evaluate", {"expression": TOUCH_FIX, "returnByValue": True}, session)
            if result["result"].get("value") is True:
                return
        except ProtocolError as error:
            if "Cannot find default execution context" not in str(error):
                raise
        time.sleep(0.15)
    raise ProtocolError("The workbench did not confirm the SCM touch-menu repair")


def watch_workbenches():
    pipe = PrivatePipe()
    sessions = {}
    pipe.request("Target.setDiscoverTargets", {"discover": True, "filter": [{"type": "page"}]})
    while True:
        event = pipe.event()
        method = event["method"]
        params = event["params"]
        if method == "Target.targetDestroyed":
            sessions.pop(params["targetId"], None)
        elif method in ("Target.targetCreated", "Target.targetInfoChanged"):
            target = params["targetInfo"]
            target_id = target["targetId"]
            if target_id in sessions or not is_workbench(target):
                continue
            session = pipe.request("Target.attachToTarget", {"targetId": target_id, "flatten": True})["sessionId"]
            try:
                pipe.request("Page.addScriptToEvaluateOnNewDocument", {"source": TOUCH_FIX, "runImmediately": True}, session)
                pipe.request("Page.enable", {}, session)
                evaluate(pipe, session)
            except ProtocolError as error:
                print(f"SCM touch-menu repair could not attach: {error}", file=sys.stderr)
                continue
            sessions[target_id] = session
            print("SCM touch-menu repair active", file=sys.stderr)
        elif method == "Page.frameNavigated" and event.get("sessionId") in sessions.values():
            frame = params["frame"]
            if "parentId" not in frame and is_workbench({"type": "page", "url": frame["url"]}):
                try:
                    evaluate(pipe, event["sessionId"])
                except ProtocolError as error:
                    print(f"SCM touch-menu repair could not reload: {error}", file=sys.stderr)
        elif method == "Target.detachedFromTarget":
            for target_id, session in tuple(sessions.items()):
                if session == params["sessionId"]:
                    sessions.pop(target_id)


if __name__ == "__main__":
    try:
        watch_workbenches()
    except (EOFError, BrokenPipeError):
        pass
    except (OSError, ValueError, ProtocolError) as error:
        print(f"SCM touch-menu repair could not continue: {error}", file=sys.stderr)
        sys.exit(1)
