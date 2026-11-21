#define _GNU_SOURCE
#include <errno.h>
#include <glib-unix.h>
#include <gmodule.h>
#include <gtk/gtk.h>
#include <stddef.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

enum { UNAVAILABLE, COMMITTED, STALE, READY };
enum { MAX_TEXT_BYTES = 16384, REQUEST_TIMEOUT_MS = 200, MAX_PEERS = 4 };

typedef struct {
    GtkIMContextSimple parent;
} TabletIMContext;

typedef struct {
    GtkIMContextSimpleClass parent;
} TabletIMContextClass;

G_DEFINE_DYNAMIC_TYPE(TabletIMContext, tablet_im_context, GTK_TYPE_IM_CONTEXT_SIMPLE)

typedef struct {
    int fd;
    guint source;
    guint timeout;
    guint64 focus;
    GtkIMContext *context;
} Request;

static GtkIMContext *focused;
static guint64 focus_serial;
static int listener = -1;
static guint listener_source;
static char *socket_path;
static guint pending;

static void reply(int fd, guint8 result)
{
    send(fd, &result, sizeof(result), MSG_NOSIGNAL);
}

static void free_request(gpointer data)
{
    Request *request = data;
    if (request->timeout)
        g_source_remove(request->timeout);
    close(request->fd);
    g_object_unref(request->context);
    g_free(request);
    pending--;
}

static gboolean expire_request(gpointer data)
{
    Request *request = data;
    request->timeout = 0;
    g_source_remove(request->source);
    return G_SOURCE_REMOVE;
}

static gboolean receive_commit(int fd, GIOCondition condition, gpointer data)
{
    Request *request = data;
    if (!(condition & G_IO_IN))
        return G_SOURCE_REMOVE;

    char text[MAX_TEXT_BYTES + 1];
    ssize_t length = recv(fd, text, MAX_TEXT_BYTES, MSG_TRUNC);
    if (length < 0 && (errno == EAGAIN || errno == EINTR))
        return G_SOURCE_CONTINUE;
    if (length <= 0)
        return G_SOURCE_REMOVE;
    if (length > MAX_TEXT_BYTES || !g_utf8_validate(text, length, NULL) ||
        focused != request->context || focus_serial != request->focus) {
        reply(fd, STALE);
        return G_SOURCE_REMOVE;
    }

    text[length] = '\0';
    g_signal_emit_by_name(request->context, "commit", text);
    reply(fd, COMMITTED);
    return G_SOURCE_REMOVE;
}

static gboolean accept_commit(int fd, GIOCondition condition, gpointer unused)
{
    (void) unused;
    if (!(condition & G_IO_IN))
        return G_SOURCE_CONTINUE;

    int peer = accept4(fd, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (peer < 0)
        return G_SOURCE_CONTINUE;
    if (!focused || pending >= MAX_PEERS) {
        reply(peer, UNAVAILABLE);
        close(peer);
        return G_SOURCE_CONTINUE;
    }

    Request *request = g_new0(Request, 1);
    request->fd = peer;
    request->context = g_object_ref(focused);
    request->focus = focus_serial;
    pending++;
    request->source = g_unix_fd_add_full(G_PRIORITY_DEFAULT_IDLE, peer,
        G_IO_IN | G_IO_HUP | G_IO_ERR, receive_commit, request, free_request);
    request->timeout = g_timeout_add(REQUEST_TIMEOUT_MS, expire_request, request);
    reply(peer, READY);
    return G_SOURCE_CONTINUE;
}

static void start_listener(void)
{
    if (listener >= 0)
        return;
    const char *path = g_getenv("TABLET_VSCODE_IME_SOCKET");
    struct sockaddr_un address = { .sun_family = AF_UNIX };
    if (!path || path[0] != '/' || strlen(path) >= sizeof(address.sun_path))
        return;
    strcpy(address.sun_path, path);

    int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0)
        return;
    if (bind(fd, (struct sockaddr *) &address, sizeof(address)) < 0) {
        close(fd);
        return;
    }
    if (listen(fd, MAX_PEERS) < 0) {
        unlink(path);
        close(fd);
        return;
    }
    listener = fd;
    socket_path = g_strdup(path);
    listener_source = g_unix_fd_add_full(G_PRIORITY_DEFAULT_IDLE, listener,
        G_IO_IN | G_IO_ERR, accept_commit, NULL, NULL);
}

static void focus_in(GtkIMContext *context)
{
    GtkIMContextClass *parent = GTK_IM_CONTEXT_CLASS(tablet_im_context_parent_class);
    if (parent->focus_in)
        parent->focus_in(context);
    focused = context;
    focus_serial++;
    start_listener();
}

static void leave_focus(GtkIMContext *context)
{
    if (focused == context) {
        focused = NULL;
        focus_serial++;
    }
}

static void focus_out(GtkIMContext *context)
{
    leave_focus(context);
    GtkIMContextClass *parent = GTK_IM_CONTEXT_CLASS(tablet_im_context_parent_class);
    if (parent->focus_out)
        parent->focus_out(context);
}

static void reset(GtkIMContext *context)
{
    if (focused == context)
        focus_serial++;
    GtkIMContextClass *parent = GTK_IM_CONTEXT_CLASS(tablet_im_context_parent_class);
    if (parent->reset)
        parent->reset(context);
}

static void dispose(GObject *object)
{
    leave_focus(GTK_IM_CONTEXT(object));
    G_OBJECT_CLASS(tablet_im_context_parent_class)->dispose(object);
}

static void tablet_im_context_init(TabletIMContext *context)
{
    (void) context;
}

static void tablet_im_context_class_init(TabletIMContextClass *klass)
{
    GtkIMContextClass *im = GTK_IM_CONTEXT_CLASS(klass);
    im->focus_in = focus_in;
    im->focus_out = focus_out;
    im->reset = reset;
    G_OBJECT_CLASS(klass)->dispose = dispose;
}

static void tablet_im_context_class_finalize(TabletIMContextClass *klass)
{
    (void) klass;
}

static const GtkIMContextInfo info = {
    "tablet-vscode", "Tablet VS Code", "", "", ""
};
static const GtkIMContextInfo *contexts[] = { &info };

G_MODULE_EXPORT void im_module_init(GTypeModule *module)
{
    tablet_im_context_register_type(module);
}

G_MODULE_EXPORT void im_module_exit(void)
{
    if (listener_source)
        g_source_remove(listener_source);
    if (listener >= 0)
        close(listener);
    if (socket_path)
        unlink(socket_path);
    g_clear_pointer(&socket_path, g_free);
    listener = -1;
    listener_source = 0;
}

G_MODULE_EXPORT void im_module_list(const GtkIMContextInfo ***list, int *count)
{
    *list = contexts;
    *count = G_N_ELEMENTS(contexts);
}

G_MODULE_EXPORT GtkIMContext *im_module_create(const gchar *name)
{
    if (g_strcmp0(name, info.context_id) != 0)
        return NULL;
    return g_object_new(tablet_im_context_get_type(), NULL);
}
