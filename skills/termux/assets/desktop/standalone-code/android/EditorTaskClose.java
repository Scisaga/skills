package com.termux.x11;

import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.os.Binder;
import android.os.Build;
import android.os.IBinder;
import android.os.Process;
import android.os.RemoteException;
import android.util.Log;
import java.io.IOException;

final class EditorTaskClose {
    private static final String LOG = "VSCodeTaskClose";
    private static final IBinder HOST_LIFETIME = new Binder();

    private static SharedPreferences tasks(Context context) {
        return context.getSharedPreferences("vscode-editor-tasks", Context.MODE_PRIVATE);
    }

    private static final class Task {
        final String session;
        final int pid;
        final int id;
        final long attachedAt;

        Task(String session, int pid, int id, long attachedAt) {
            this.session = session;
            this.pid = pid;
            this.id = id;
            this.attachedAt = attachedAt;
        }

        static Task read(Context context, String tag) {
            String value = tasks(context).getString(tag, "");
            String[] fields = value.split(" ", -1);
            if (fields.length != 4 || !fields[0].matches("[0-9a-f]{32}")) {
                return null;
            }
            try {
                return new Task(fields[0], Integer.parseInt(fields[1]), Integer.parseInt(fields[2]),
                        Long.parseLong(fields[3]));
            } catch (NumberFormatException invalid) {
                return null;
            }
        }

        void write(Context context, String tag) {
            // Keep the attachment available after Android kills this process.
            tasks(context).edit().putString(tag, session + " " + pid + " " + id + " " + attachedAt).commit();
        }
    }

    static void attached(MainActivity activity) {
        String tag = activity.getTag();
        if (!CodeLauncher.isWindowTag(tag) || activity.service == null || activity.isFinishing()) {
            return;
        }
        try {
            String session = activity.service.editorSessionToken();
            if (session == null || !session.matches("[0-9a-f]{32}")) {
                return;
            }
            Task previous = Task.read(activity, tag);
            int pid = Process.myPid();
            int id = activity.getTaskId();
            if (previous == null || previous.pid != pid || previous.id != id || !previous.session.equals(session)) {
                new Task(session, pid, id, System.currentTimeMillis()).write(activity, tag);
                Log.d(LOG, "Tracking " + tag + " task " + id);
            }
            activity.service.watchEditorHost(HOST_LIFETIME);
        } catch (RemoteException | RuntimeException disconnected) {
            Log.d(LOG, "Editor connection closed while recording " + tag);
        }
    }

    static void finished(MainActivity activity) {
        String tag = activity.getTag();
        if (!CodeLauncher.isWindowTag(tag) || !activity.isFinishing() || activity.isChangingConfigurations()
                || activity.service == null) {
            return;
        }
        Task task = Task.read(activity, tag);
        if (task != null && task.pid == Process.myPid() && task.id == activity.getTaskId()) {
            request(activity, tag, activity.service, task);
        }
    }

    static void reconnect(Context context, String tag, IBinder binder) {
        if (!CodeLauncher.isWindowTag(tag)) {
            return;
        }
        Task task = Task.read(context, tag);
        if (task == null || task.pid <= 0) {
            return;
        }
        ActivityManager manager = context.getSystemService(ActivityManager.class);
        if (manager == null) {
            return;
        }
        for (ActivityManager.AppTask candidate : manager.getAppTasks()) {
            ActivityManager.RecentTaskInfo info = candidate.getTaskInfo();
            if (info != null && ((Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q ? info.taskId : info.id) == task.id
                    || (info.baseIntent != null && tag.equals(info.baseIntent.getDataString())))) {
                return;
            }
        }
        ICmdEntryInterface connection = ICmdEntryInterface.Stub.asInterface(binder);
        if (task.pid == Process.myPid()) {
            request(context, tag, connection, task);
            return;
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return;
        }
        // The system may destroy the task and kill its host before onDestroy runs.
        for (ApplicationExitInfo exit : manager.getHistoricalProcessExitReasons(context.getPackageName(), task.pid, 1)) {
            if (exit.getTimestamp() >= task.attachedAt && wasRemovedByUser(exit)) {
                request(context, tag, connection, task);
            }
        }
    }

    private static boolean wasRemovedByUser(ApplicationExitInfo exit) {
        if (exit.getReason() == ApplicationExitInfo.REASON_USER_REQUESTED) {
            return true;
        }
        if (exit.getReason() != ApplicationExitInfo.REASON_OTHER) {
            return false;
        }
        // HyperOS records removal from Recents as a system kill with this exact description.
        String description = exit.getDescription();
        return description != null && (description.equals("SwipeUpClean") || description.endsWith("] SwipeUpClean"));
    }

    private static void request(Context context, String tag, ICmdEntryInterface service, Task task) {
        try {
            if (service.closeEditor(task.session)) {
                forget(context, tag);
                Log.i(LOG, "Requested normal editor close for " + tag);
            }
        } catch (RemoteException | RuntimeException disconnected) {
            Log.d(LOG, "Editor connection closed while requesting close for " + tag);
        }
    }

    static void forget(Context context, String tag) {
        if (CodeLauncher.isWindowTag(tag)) {
            tasks(context).edit().remove(tag).apply();
        }
    }

    // These two methods run in the Termux X server, across the existing Binder connection.
    static String termuxSessionToken() {
        String token = System.getenv("TABLET_VSCODE_WINDOW_TOKEN");
        if (token == null || !token.matches("[0-9a-f]{32}")) {
            return null;
        }
        try {
            String[] packages = android.app.ActivityThread.getPackageManager().getPackagesForUid(Binder.getCallingUid());
            if (packages != null) {
                for (String name : packages) {
                    if (BuildConfig.APPLICATION_ID.equals(name)) {
                        return token;
                    }
                }
            }
        } catch (RemoteException | SecurityException failed) {
            Log.w(LOG, "Could not verify the editor host", failed);
        }
        return null;
    }

    static boolean closeInTermux(String tag, String token) {
        return token != null && token.equals(termuxSessionToken()) && launchCloser(tag, false);
    }

    static void closeStoppedHost(String tag) {
        try {
            // A stopped package may never receive the X11 reconnect broadcast.
            PackageInfo host = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                    ? android.app.ActivityThread.getPackageManager().getPackageInfo(BuildConfig.APPLICATION_ID, 0L, 0)
                    : android.app.ActivityThread.getPackageManager().getPackageInfo(BuildConfig.APPLICATION_ID, 0, 0);
            if (host != null && host.applicationInfo != null
                    && (host.applicationInfo.flags & ApplicationInfo.FLAG_STOPPED) != 0) {
                Log.i(LOG, "Android host stopped after attachment for " + tag);
                launchCloser(tag, true);
            }
        } catch (RemoteException | SecurityException failed) {
            Log.w(LOG, "Could not read the stopped state of the editor host", failed);
        }
    }

    private static boolean launchCloser(String tag, boolean requireSoleSession) {
        if (!CodeLauncher.isWindowTag(tag)) {
            return false;
        }
        String prefix = System.getenv("PREFIX");
        String helper = System.getenv("TABLET_VSCODE_CLOSE_HELPER");
        String state = System.getenv("TABLET_VSCODE_CLOSE_STATE");
        String display = System.getenv("DISPLAY");
        String container = System.getenv("TABLET_VSCODE_CLOSE_CONTAINER");
        String user = System.getenv("TABLET_VSCODE_CLOSE_USER");
        if (prefix == null || helper == null || state == null || display == null || container == null || user == null) {
            return false;
        }
        try {
            ProcessBuilder close = new ProcessBuilder(prefix + "/bin/python", helper, "close", display, tag, state,
                    "--container", container, "--user", user);
            if (requireSoleSession) {
                close.command().add("--sole-session");
            }
            close.inheritIO().start();
            return true;
        } catch (IOException | SecurityException failed) {
            Log.w(LOG, "Could not request close for " + tag, failed);
            return false;
        }
    }
}
