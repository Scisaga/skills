/* Direct-touch secondary click for Xfdesktop/Thunar. Never grabs touch input. */
#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XInput2.h>
#include <X11/extensions/XTest.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/select.h>
#include <time.h>
#include <unistd.h>

typedef struct { int id, valid; double min[2], max[2], current[2]; } TouchDevice;
typedef struct { int source, detail; } Contact;
static TouchDevice devices[128];
static int device_count, contact_count, armed, candidate_source, candidate_detail;
static int start_x, start_y, width, height, hold_ms = 700, move_px = 24;
static double began, pending_at;
static Window candidate_window, root;
static volatile sig_atomic_t stopping;
static Contact contacts[128];
static Display *display;
static void stop_signal(int value) { (void)value; stopping = 1; }

static double now(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return value.tv_sec + value.tv_nsec / 1000000000.;
}

static int ignore_xerror(Display *d, XErrorEvent *e) { (void)d; (void)e; return 0; }

static void query_devices(void) {
    int count;
    XIDeviceInfo *all = XIQueryDevice(display, XIAllDevices, &count);
    device_count = 0;
    for (int i = 0; all && i < count && device_count < 128; ++i) {
        int direct = 0;
        TouchDevice device = {.id = all[i].deviceid};
        for (int j = 0; j < all[i].num_classes; ++j) {
            XIAnyClassInfo *info = all[i].classes[j];
            if (info->type == XITouchClass && ((XITouchClassInfo *)info)->mode == XIDirectTouch)
                direct = 1;
            if (info->type == XIValuatorClass) {
                XIValuatorClassInfo *axis = (XIValuatorClassInfo *)info;
                if (axis->number < 2 && axis->number >= 0 && axis->mode == XIModeAbsolute) {
                    device.min[axis->number] = axis->min;
                    device.max[axis->number] = axis->max;
                    device.current[axis->number] = axis->value;
                    device.valid |= 1 << axis->number;
                }
            }
        }
        if (direct && device.valid == 3 && device.max[0] > device.min[0] && device.max[1] > device.min[1])
            devices[device_count++] = device;
    }
    if (all) XIFreeDeviceInfo(all);
}

static int position(XIRawEvent *event, int *x, int *y) {
    TouchDevice *device = NULL;
    for (int i = 0; i < device_count; ++i)
        if (devices[i].id == event->sourceid) device = &devices[i];
    if (!device) return 0;
    int offset = 0;
    for (int axis = 0; axis < event->valuators.mask_len * 8; ++axis) {
        if (!XIMaskIsSet(event->valuators.mask, axis)) continue;
        if (axis < 2) device->current[axis] = event->raw_values[offset];
        ++offset;
    }
    *x = (int)lround((device->current[0] - device->min[0]) / (device->max[0] - device->min[0]) * (width - 1));
    *y = (int)lround((device->current[1] - device->min[1]) / (device->max[1] - device->min[1]) * (height - 1));
    return *x >= 0 && *y >= 0 && *x < width && *y < height;
}

static Window eligible_window(int x, int y) {
    Window window = root;
    for (int depth = 0; depth < 24; ++depth) {
        XClassHint hint = {0};
        if (XGetClassHint(display, window, &hint)) {
            int kind = hint.res_class && (!strcasecmp(hint.res_class, "Thunar") || !strcasecmp(hint.res_class, "Xfdesktop"));
            if (hint.res_name) XFree(hint.res_name);
            if (hint.res_class) XFree(hint.res_class);
            if (kind) return window;
        }
        Window child = None;
        int local_x, local_y;
        if (!XTranslateCoordinates(display, root, window, x, y, &local_x, &local_y, &child) || child == None)
            break;
        window = child;
    }
    return None;
}

static void touch(XIRawEvent *event, int type) {
    int x = start_x, y = start_y;
    int located = position(event, &x, &y);
    if (type == XI_RawTouchBegin) {
        pending_at = 0;
        if (contact_count < 128) contacts[contact_count++] = (Contact){event->sourceid, event->detail};
        if (contact_count != 1 || !located) { armed = 0; return; }
        candidate_window = eligible_window(x, y);
        armed = candidate_window != None;
        candidate_source = event->sourceid;
        candidate_detail = event->detail;
        start_x = x; start_y = y; began = now();
    } else if (type == XI_RawTouchUpdate) {
        if (armed && event->sourceid == candidate_source && event->detail == candidate_detail &&
            (!located || hypot(x - start_x, y - start_y) > move_px)) armed = 0;
    } else {
        int qualified = armed && contact_count == 1 && event->sourceid == candidate_source &&
            event->detail == candidate_detail && now() - began >= hold_ms / 1000.;
        if (located && hypot(x - start_x, y - start_y) > move_px) qualified = 0;
        armed = 0;
        for (int i = 0; i < contact_count; ++i) {
            if (contacts[i].source == event->sourceid && contacts[i].detail == event->detail) {
                contacts[i] = contacts[--contact_count]; break;
            }
        }
        /* Wait for the genuine primary-button release; do not synthesize one. */
        if (qualified && contact_count == 0) pending_at = now() + .08;
    }
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--hold-ms") && i + 1 < argc) hold_ms = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--move-px") && i + 1 < argc) move_px = atoi(argv[++i]);
        else { fprintf(stderr, "Usage: tablet-touch-longpress [--hold-ms 700] [--move-px 24]\n"); return 2; }
    }
    if (hold_ms < 400 || hold_ms > 3000 || move_px < 4 || move_px > 80) return 2;
    display = XOpenDisplay(NULL);
    if (!display) { fprintf(stderr, "Cannot open current X11 display\n"); return 1; }
    XSetErrorHandler(ignore_xerror);
    signal(SIGTERM, stop_signal); signal(SIGINT, stop_signal);
    int opcode, event_base, error_base, major = 2, minor = 2;
    if (!XQueryExtension(display, "XInputExtension", &opcode, &event_base, &error_base) ||
        XIQueryVersion(display, &major, &minor) != Success || major < 2 || (major == 2 && minor < 2) ||
        !XTestQueryExtension(display, &event_base, &error_base, &major, &minor)) {
        fprintf(stderr, "XInput 2.2 and XTest are required\n"); return 1;
    }
    int screen = DefaultScreen(display);
    root = RootWindow(display, screen);
    width = DisplayWidth(display, screen); height = DisplayHeight(display, screen);
    Atom singleton = XInternAtom(display, "_SCISAGA_TABLET_LONGPRESS", False);
    if (XGetSelectionOwner(display, singleton) != None) { XCloseDisplay(display); return 0; }
    Window sentinel = XCreateSimpleWindow(display, root, -1, -1, 1, 1, 0, 0, 0);
    XSetSelectionOwner(display, singleton, sentinel, CurrentTime);
    XSync(display, False);
    if (XGetSelectionOwner(display, singleton) != sentinel) { XCloseDisplay(display); return 0; }
    unsigned char bits[XIMaskLen(XI_LASTEVENT)] = {0};
    XISetMask(bits, XI_RawTouchBegin); XISetMask(bits, XI_RawTouchUpdate); XISetMask(bits, XI_RawTouchEnd);
    XIEventMask mask = {XIAllMasterDevices, sizeof(bits), bits};
    XISelectEvents(display, root, &mask, 1);
    XSelectInput(display, root, StructureNotifyMask);
    query_devices();
    XFlush(display);
    while (!stopping) {
        while (XPending(display)) {
            XEvent event;
            XNextEvent(display, &event);
            if (event.type == SelectionClear) { stopping = 1; break; }
            if (event.type == ConfigureNotify && event.xconfigure.window == root) {
                width = event.xconfigure.width; height = event.xconfigure.height;
                armed = 0; pending_at = 0;
            }
            XGenericEventCookie *cookie = &event.xcookie;
            if (event.type == GenericEvent && cookie->extension == opcode && XGetEventData(display, cookie)) {
                if (cookie->evtype >= XI_RawTouchBegin && cookie->evtype <= XI_RawTouchEnd)
                    touch((XIRawEvent *)cookie->data, cookie->evtype);
                XFreeEventData(display, cookie);
            }
        }
        if (pending_at && now() >= pending_at) {
            pending_at = 0;
            Window r, child; int rx, ry, wx, wy; unsigned int buttons;
            if (!contact_count && eligible_window(start_x, start_y) == candidate_window &&
                XQueryPointer(display, root, &r, &child, &rx, &ry, &wx, &wy, &buttons) && !(buttons & Button1Mask)) {
                XTestFakeMotionEvent(display, screen, start_x, start_y, CurrentTime);
                XTestFakeButtonEvent(display, 3, True, CurrentTime);
                XTestFakeButtonEvent(display, 3, False, CurrentTime);
                XFlush(display);
            }
        }
        struct timeval wait, *timeout = NULL;
        if (pending_at) {
            double remaining = fmax(0, pending_at - now());
            wait.tv_sec = (time_t)remaining;
            wait.tv_usec = (suseconds_t)((remaining - wait.tv_sec) * 1000000);
            timeout = &wait;
        }
        fd_set read_set;
        FD_ZERO(&read_set); FD_SET(ConnectionNumber(display), &read_set);
        if (select(ConnectionNumber(display) + 1, &read_set, NULL, NULL, timeout) < 0) break;
    }
    XCloseDisplay(display);
    return 0;
}
