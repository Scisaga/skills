package com.termux.x11;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class CodeLauncher extends Activity {
    static final String ACTION_TITLE = "com.scisaga.tabletvscode.WINDOW_TITLE";
    static final String ACTION_NEW_REQUEST = "com.scisaga.tabletvscode.NEW_WINDOW_REQUEST";
    private static final String ACTION_NEW = "com.scisaga.tabletvscode.NEW_WINDOW";
    private static final String ACTION_READY = "com.scisaga.tabletvscode.WINDOW_READY";
    private static final String PERMISSION = "com.termux.permission.RUN_COMMAND";
    private static final String COMMAND = "/data/data/com.termux/files/home/.local/libexec/tablet-vscode/open";
    private static final String EXTRA = "com.termux.RUN_COMMAND_";
    private static final int REQUEST_TERMUX = 1;
    private static final String LINUX_APP_NAME = "Visual Studio Code";
    private boolean newWindow;
    private String launchRequest;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable launchTimeout = this::launchFailed;
    private final BroadcastReceiver windowReady = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String tag = intent.getStringExtra(CmdEntryPoint.EXTRA_DOCUMENT_TAG);
            if (launchRequest == null || !launchRequest.equals(intent.getStringExtra("launch_request"))
                    || !isWindowTag(tag) || isFinishing()) {
                return;
            }
            try {
                startActivity(editorIntent(tag).putExtra("editor_title", intent.getStringExtra("editor_title")),
                        MainActivity.freeformActivityOptions());
                if (startService(runCommand("ack", "", launchRequest)) == null) {
                    launchFailed();
                    return;
                }
                String token = intent.getStringExtra("editor_token");
                if (token != null && token.matches("[0-9a-f]{32}")) {
                    windowTitles(context).edit().putString("token:" + tag, token).apply();
                }
                if (isOrderedBroadcast()) {
                    setResultCode(RESULT_OK);
                }
                finish();
            } catch (ActivityNotFoundException | SecurityException error) {
                launchFailed();
            }
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        newWindow = ACTION_NEW.equals(getIntent().getAction())
                || (Intent.ACTION_MAIN.equals(getIntent().getAction())
                    && (getIntent().getFlags() & Intent.FLAG_ACTIVITY_MULTIPLE_TASK) != 0);
        List<String> windows = getEditorWindowTags();
        if (newWindow || windows.isEmpty()) {
            requestLaunch();
        } else if (windows.size() == 1) {
            focus(windows.get(0));
        } else {
            String[] labels = new String[windows.size()];
            for (int index = 0; index < windows.size(); index++) {
                labels[index] = windowLabel(this, windows.get(index));
            }
            new AlertDialog.Builder(this)
                    .setTitle(R.string.vscode_windows)
                    .setItems(labels, (dialog, position) -> focus(windows.get(position)))
                    .setNeutralButton(R.string.vscode_new_window, (dialog, which) -> {
                        newWindow = true;
                        requestLaunch();
                    })
                    .setOnCancelListener(dialog -> finish())
                    .show();
        }
    }

    private List<String> getEditorWindowTags() {
        List<String> result = new ArrayList<>();
        for (ActivityManager.AppTask task : getSystemService(ActivityManager.class).getAppTasks()) {
            ActivityManager.RecentTaskInfo info = task.getTaskInfo();
            String tag = info == null || info.baseIntent == null ? null : info.baseIntent.getDataString();
            MainActivity editor = connectedEditor(tag);
            if (editor != null && info.taskId == editor.getTaskId()) {
                result.add(tag);
            }
        }
        return result;
    }

    private static MainActivity connectedEditor(String tag) {
        MainActivity editor = isWindowTag(tag) ? MainActivity.getInstance(tag) : null;
        if (editor == null || editor.isFinishing() || editor.isDestroyed() || editor.service == null
                || !editor.service.asBinder().isBinderAlive()) {
            return null;
        }
        return editor;
    }

    private void focus(String tag) {
        if (connectedEditor(tag) == null) {
            requestLaunch();
            return;
        }
        // The tagged activity's document launch mode matches this URI to the existing task.
        try {
            startActivity(editorIntent(tag));
            finish();
        } catch (ActivityNotFoundException | SecurityException error) {
            requestLaunch();
        }
    }

    private Intent editorIntent(String tag) {
        return new Intent(this, MainActivity.MainActivityTagged.class)
                .setData(Uri.parse(tag))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    }

    static void openNewWindow(MainActivity editor) {
        editor.startActivity(new Intent(editor, CodeLauncher.class).setAction(ACTION_NEW)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
    }

    static boolean requestNewWindow(Context context, Intent intent) {
        String tag = intent.getStringExtra(CmdEntryPoint.EXTRA_DOCUMENT_TAG);
        MainActivity editor = connectedEditor(tag);
        String token = intent.getStringExtra("editor_token");
        if (editor == null || !editor.hasWindowFocus() || token == null
                || !token.equals(windowTitles(context).getString("token:" + tag, null))) {
            return false;
        }
        openNewWindow(editor);
        return true;
    }

    private void requestLaunch() {
        if (checkSelfPermission(PERMISSION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{PERMISSION}, REQUEST_TERMUX);
        } else {
            launch();
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(requestCode, permissions, grants);
        if (requestCode == REQUEST_TERMUX && grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED) {
            launch();
        } else {
            launchFailed();
        }
    }

    private void launch() {
        if (launchRequest != null) {
            return;
        }
        IntentFilter ready = new IntentFilter(ACTION_READY);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(windowReady, ready, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(windowReady, ready);
        }
        launchRequest = UUID.randomUUID().toString().replace("-", "");
        try {
            if (startService(runCommand(newWindow ? "new" : "open", "", launchRequest)) == null) {
                launchFailed();
            } else {
                handler.postDelayed(launchTimeout, 15000);
            }
        } catch (IllegalStateException | SecurityException | ActivityNotFoundException error) {
            launchFailed();
        }
    }

    private Intent runCommand(String... arguments) {
        return new Intent("com.termux.RUN_COMMAND")
                .setClassName("com.termux", "com.termux.app.RunCommandService")
                .putExtra(EXTRA + "PATH", COMMAND)
                .putExtra(EXTRA + "ARGUMENTS", arguments)
                .putExtra(EXTRA + "BACKGROUND", true)
                .putExtra(EXTRA + "COMMAND_LABEL", getString(R.string.vscode_app_name));
    }

    @Override
    protected void onStop() {
        super.onStop();
        if (launchRequest != null) {
            finish();
        }
    }

    @Override
    protected void onDestroy() {
        if (launchRequest != null) {
            handler.removeCallbacks(launchTimeout);
            unregisterReceiver(windowReady);
            launchRequest = null;
        }
        super.onDestroy();
    }

    private void launchFailed() {
        Toast.makeText(this, R.string.vscode_launch_failed, Toast.LENGTH_LONG).show();
        finish();
    }

    static boolean isWindowTag(String tag) {
        return tag != null && tag.matches("vscode-[0-9]{1,2}");
    }

    private static SharedPreferences windowTitles(Context context) {
        return context.getSharedPreferences("vscode-window-titles", Context.MODE_PRIVATE);
    }

    private static String windowLabel(Context context, String tag) {
        return windowTitles(context).getString(tag, context.getString(R.string.vscode_new_window));
    }

    static void updateTaskTitle(Context context, String tag, String name, boolean editorTitle) {
        if (!isWindowTag(tag) || name == null || name.length() > 160) {
            return;
        }
        String title = name.replaceAll("[\\p{Cntrl}]", " ").trim();
        String key = editorTitle ? "editor:" + tag : tag;
        SharedPreferences values = windowTitles(context);
        if (title.equals(values.getString(key, ""))) {
            return;
        }
        SharedPreferences.Editor titles = values.edit();
        (title.isEmpty() ? titles.remove(key) : titles.putString(key, title)).apply();
        if (!editorTitle && values.contains("editor:" + tag)) {
            return;
        }
        MainActivity activity = MainActivity.getInstance(tag);
        if (activity != null) {
            applyTaskTitle(activity);
        }
    }

    static void clearTaskTitle(Context context, String tag) {
        if (isWindowTag(tag)) {
            windowTitles(context).edit().remove(tag).remove("editor:" + tag).remove("token:" + tag).apply();
        }
    }

    static void initializeTaskTitle(MainActivity activity) {
        String tag = activity.getTag();
        String title = activity.getIntent().getStringExtra("editor_title");
        if (isWindowTag(tag) && title != null && title.length() <= 160) {
            title = title.replaceAll("[\\p{Cntrl}]", " ").trim();
            if (!title.isEmpty()) {
                windowTitles(activity).edit().putString("editor:" + tag, title).apply();
            }
        }
        applyTaskTitle(activity);
    }

    static void applyTaskTitle(MainActivity activity) {
        String tag = activity.getTag();
        if (!isWindowTag(tag)) {
            return;
        }
        SharedPreferences values = windowTitles(activity);
        String appName = activity.getString(R.string.vscode_app_name);
        String title = values.getString("editor:" + tag,
                values.getString(tag, appName));
        if (LINUX_APP_NAME.equals(title)) {
            title = appName;
        }
        activity.setTitle(title);
        // Use the application icon so ZUI normalizes it the same way as the pinned Dock icon.
        activity.setTaskDescription(new ActivityManager.TaskDescription(title));
    }
}
