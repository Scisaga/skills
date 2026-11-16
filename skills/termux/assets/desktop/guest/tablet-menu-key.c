/* Observe a standalone Super release without grabbing any application keys. */
#include <X11/Xlib.h>
#include <X11/XKBlib.h>
#include <X11/extensions/XInput2.h>
#include <X11/keysym.h>
#include <signal.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

static double seconds(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1000000000.0;
}

int main(int argc, char **argv) {
    if (argc != 2 || argv[1][0] != '/') return 2;
    Display *d = XOpenDisplay(NULL);
    if (!d) return 3;
    /* XI2.1+ also delivers raw keys while another client (a menu) holds a grab. */
    int opcode, event, error, major = 2, minor = 2;
    if (!XQueryExtension(d, "XInputExtension", &opcode, &event, &error) ||
        XIQueryVersion(d, &major, &minor) != Success) return 4;
    Atom selection = XInternAtom(d, "_SCISAGA_STANDALONE_MENU_KEY", False);
    if (XGetSelectionOwner(d, selection) != None) { XCloseDisplay(d); return 0; }
    Window owner = XCreateSimpleWindow(d, DefaultRootWindow(d), 0, 0, 1, 1, 0, 0, 0);
    XSetSelectionOwner(d, selection, owner, CurrentTime);
    XSync(d, False);
    if (XGetSelectionOwner(d, selection) != owner) return 0;
    unsigned char bits[XIMaskLen(XI_RawKeyRelease)] = {0};
    XISetMask(bits, XI_RawKeyPress);
    XISetMask(bits, XI_RawKeyRelease);
    XIEventMask mask = { XIAllMasterDevices, sizeof(bits), bits };
    XISelectEvents(d, DefaultRootWindow(d), &mask, 1);
    XSync(d, False);
    signal(SIGCHLD, SIG_IGN);
    int held = 0, candidate = 0;
    double began = 0;
    for (;;) {
        XEvent e;
        XNextEvent(d, &e);
        if (e.type == SelectionClear) break;
        if (e.type != GenericEvent || e.xcookie.extension != opcode || !XGetEventData(d, &e.xcookie)) continue;
        XIRawEvent *raw = e.xcookie.data;
        int type = e.xcookie.evtype, code = raw->detail;
        KeySym sym = XkbKeycodeToKeysym(d, code, 0, 0);
        int super = sym == XK_Super_L || sym == XK_Super_R;
        if (type == XI_RawKeyPress) {
            if (super && !held) {
                char keys[32];
                XQueryKeymap(d, keys);
                candidate = 1;
                for (int k = 0; k < 256; ++k)
                    if (k != code && (keys[k / 8] & (1 << (k % 8)))) candidate = 0;
                held = code;
                began = seconds();
            } else if (code != held) {
                candidate = 0;
            }
        } else if (type == XI_RawKeyRelease && code == held) {
            char keys[32];
            XQueryKeymap(d, keys);
            if (!(keys[code / 8] & (1 << (code % 8)))) {
                int trigger = candidate && seconds() - began <= 2.0;
                held = candidate = 0;
                if (trigger && fork() == 0) {
                    close(ConnectionNumber(d));
                    execl(argv[1], argv[1], "menu-toggle", (char *)NULL);
                    _exit(127);
                }
            }
        }
        XFreeEventData(d, &e.xcookie);
    }
    XCloseDisplay(d);
    return 0;
}
