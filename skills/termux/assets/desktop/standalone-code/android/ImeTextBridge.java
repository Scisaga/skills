package com.termux.x11;

import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.util.Log;

import java.io.IOException;

/** Delivers one Android IME commit to the Gtk input context of this X11 session. */
final class ImeTextBridge {
    static final int UNAVAILABLE = 0;
    static final int COMMITTED = 1;
    static final int STALE = 2;
    private static final int READY = 3;
    private static final int MAX_BYTES = 16384;
    private static final int REPLY_TIMEOUT_MS = 180;

    private ImeTextBridge() {}

    static boolean isTextCommit(CharSequence text) {
        if (text.length() == 0 || text.length() > MAX_BYTES / 4)
            return false;
        boolean nonAscii = false;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (Character.isISOControl(c))
                return false;
            nonAscii |= c >= 128;
        }
        return nonAscii;
    }

    static int commit(String endpoint, byte[] text) {
        if (endpoint == null || text == null || text.length == 0 || text.length > MAX_BYTES)
            return UNAVAILABLE;
        boolean sent = false;
        try (LocalSocket socket = new LocalSocket(LocalSocket.SOCKET_SEQPACKET)) {
            socket.connect(new LocalSocketAddress(endpoint, LocalSocketAddress.Namespace.FILESYSTEM));
            socket.setSoTimeout(REPLY_TIMEOUT_MS);
            if (socket.getInputStream().read() != READY)
                return UNAVAILABLE;
            sent = true;
            socket.getOutputStream().write(text);
            if (socket.getInputStream().read() == COMMITTED) {
                Log.d("TabletIme", "Committed " + text.length + " UTF-8 bytes through Gtk");
                return COMMITTED;
            }
            return STALE;
        } catch (IOException error) {
            // A missing endpoint permits key-event fallback. An in-flight commit may already be applied.
            return sent ? STALE : UNAVAILABLE;
        }
    }
}
