package com.scisaga.tabletdesktop;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.DialogInterface;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.CompoundButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;

public final class ManagerActivity extends Activity {
    static ManagerActivity active;
    private float density;
    private LinearLayout root, actions;
    private TextView title, subtitle;
    private final ArrayList<Button> buttons = new ArrayList<Button>();
    private final Handler handler = new Handler();
    private JSONObject state = new JSONObject();
    private static int serial = (int)(System.currentTimeMillis() & 0x3fffffff);
    private int pending = 0;
    private boolean busy = false;
    private boolean pendingDesktopStart = false;
    private static final int TEXT = Color.rgb(238, 242, 248);
    private static final int MUTED = Color.rgb(167, 181, 199);
    private int dp(float n) { return (int)(n * density + .5f); }

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        active = this;
        density = getResources().getDisplayMetrics().density;
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
        handleEntry(getIntent());
    }

    @Override public void onDestroy() {
        if (active == this) active = null;
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    @Override public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleEntry(intent);
    }

    private void handleEntry(Intent intent) {
        boolean desktop = intent != null && intent.getComponent() != null
            && intent.getComponent().getClassName().equals("com.scisaga.tabletdesktop.DesktopEntry");
        if (busy) {
            if (desktop) pendingDesktopStart = true;
            return;
        }
        pendingDesktopStart = false;
        renderMain();
        if (desktop) {
            title.setText("Linux \u684c\u9762");
            subtitle.setText("\u6b63\u5728\u542f\u52a8\u6216\u8fd4\u56de\u684c\u9762\u2026");
        }
        execute(desktop ? "start" : "status");
    }

    private GradientDrawable background(int color, int radius) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(dp(radius));
        return d;
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView v = new TextView(this);
        v.setText(value); v.setTextSize(size); v.setTextColor(color);
        if (bold) v.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        v.setLineSpacing(dp(4), 1);
        return v;
    }

    private void base(String heading) {
        buttons.clear();
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(25), dp(24), dp(25), dp(20));
        root.setFocusableInTouchMode(true);
        root.setBackgroundDrawable(background(Color.rgb(34, 41, 51), 22));
        title = text(heading, 21, TEXT, true);
        root.addView(title, new LinearLayout.LayoutParams(-1, -2));
        subtitle = text("\u6b63\u5728\u8bfb\u53d6\u72b6\u6001\u2026", 14, MUTED, false);
        LinearLayout.LayoutParams sub = new LinearLayout.LayoutParams(-1, -2);
        sub.topMargin = dp(11);
        root.addView(subtitle, sub);
        View divider = new View(this);
        divider.setBackgroundColor(Color.rgb(63, 75, 92));
        LinearLayout.LayoutParams line = new LinearLayout.LayoutParams(-1, dp(1));
        line.topMargin = dp(20); line.bottomMargin = dp(10);
        root.addView(divider, line);
        actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.VERTICAL);
        root.addView(actions, new LinearLayout.LayoutParams(-1, -2));
        setContentView(root);
        int width = Math.min(dp(410), getResources().getDisplayMetrics().widthPixels - dp(48));
        getWindow().setLayout(width, -2);
        getWindow().setGravity(Gravity.CENTER);
        root.requestFocus();
    }

    private void button(String label, final String action, int style) {
        Button b = new Button(this);
        b.setText(label); b.setTextSize(16); b.setAllCaps(false);
        b.setGravity(Gravity.CENTER);
        b.setMinHeight(0); b.setMinimumHeight(0); b.setPadding(dp(16), 0, dp(16), 0);
        int color = style == 1 ? Color.rgb(58, 115, 210) : style == 2 ? Color.rgb(76, 42, 47) : Color.rgb(47, 58, 73);
        b.setBackgroundDrawable(background(color, 11));
        b.setTextColor(style == 2 ? Color.rgb(255, 184, 185) : TEXT);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, dp(51));
        p.topMargin = dp(10);
        actions.addView(b, p);
        if (!action.equals("close")) buttons.add(b);
        b.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                if (action.equals("close")) { finish(); return; }
                if (action.equals("back")) { renderMain(); execute("status"); return; }
                if (action.equals("force")) {
                    new AlertDialog.Builder(ManagerActivity.this)
                        .setTitle("\u5f3a\u5236\u7ed3\u675f\u684c\u9762")
                        .setMessage("\u5c06\u7ed3\u675f\u672c\u6b21\u684c\u9762\u53ca\u6240\u5c5e\u5e94\u7528\u3002\n\u672a\u4fdd\u5b58\u5185\u5bb9\u53ef\u80fd\u4e22\u5931\u3002")
                        .setNegativeButton("\u53d6\u6d88", null)
                        .setPositiveButton("\u5f3a\u5236\u7ed3\u675f", new DialogInterface.OnClickListener() {
                            public void onClick(DialogInterface d, int which) { execute("force-stop"); }
                        }).show();
                    return;
                }
                execute(action);
            }
        });
    }

    private void renderMain() {
        base("Linux \u684c\u9762\u7ba1\u7406");
        button("\u542f\u52a8 / \u8fd4\u56de\u684c\u9762", "start", 1);
        button("\u6b63\u5e38\u7ed3\u675f\u684c\u9762", "stop", 0);
        button("\u67e5\u770b\u68c0\u67e5\u8bb0\u5f55", "events", 0);
        button("\u5f3a\u5236\u7ed3\u675f\u684c\u9762", "force", 2);
        final CheckBox boot = new CheckBox(this);
        boot.setText("\u5f00\u673a\u6062\u590d\u540e\u53f0\u670d\u52a1");
        boot.setTextSize(15); boot.setTextColor(TEXT);
        boot.setChecked(BootReceiver.enabled(this));
        LinearLayout.LayoutParams bootLayout = new LinearLayout.LayoutParams(-1, -2);
        bootLayout.topMargin = dp(14);
        actions.addView(boot, bootLayout);
        TextView bootHint = text("\u89e3\u9501\u540e\u6062\u590d\u670d\u52a1\uff0c\u684c\u9762\u6309\u9700\u8fdb\u5165", 12, MUTED, false);
        String bootStatus = BootReceiver.preferences(this).getString("status", "");
        if (bootStatus.equals("ok")) bootHint.append("\n\u4e0a\u6b21\u5f00\u673a\u6062\u590d\u5df2\u5b8c\u6210");
        if (bootStatus.equals("failed")) bootHint.append("\n\u4e0a\u6b21\u6062\u590d\u672a\u5b8c\u6210\uff0c\u8bf7\u68c0\u67e5\u81ea\u542f\u52a8\u6743\u9650");
        actions.addView(bootHint, new LinearLayout.LayoutParams(-1, -2));
        boot.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            public void onCheckedChanged(CompoundButton view, boolean checked) {
                try { BootReceiver.configure(ManagerActivity.this, checked); }
                catch (Exception e) {
                    boot.setOnCheckedChangeListener(null);
                    boot.setChecked(BootReceiver.enabled(ManagerActivity.this));
                    boot.setOnCheckedChangeListener(this);
                    Toast.makeText(ManagerActivity.this, "\u65e0\u6cd5\u4fdd\u5b58\u5f00\u673a\u6062\u590d\u8bbe\u7f6e", Toast.LENGTH_SHORT).show();
                }
            }
        });
        button("\u5173\u95ed\u7ba1\u7406", "close", 0);
        showState();
    }

    private String phase(String p) {
        if (p.equals("running")) return "\u8fd0\u884c\u4e2d";
        if (p.equals("stopped")) return "\u5df2\u7ed3\u675f";
        if (p.equals("starting")) return "\u542f\u52a8\u4e2d";
        if (p.equals("closing")) return "\u7b49\u5f85\u5173\u95ed\u5e94\u7528";
        if (p.equals("stopping")) return "\u6b63\u5728\u7ed3\u675f";
        return "\u9700\u8981\u68c0\u67e5";
    }

    private void showState() {
        if (!state.has("phase")) return;
        String s = phase(state.optString("phase"));
        if (state.has("battery_percentage")) s += "  \u00b7  \u7535\u91cf " + state.optInt("battery_percentage") + "%";
        subtitle.setText(s);
        if (!busy && buttons.size() >= 4) {
            boolean available = !state.optString("phase").equals("stopped");
            buttons.get(1).setEnabled(available);
            buttons.get(3).setEnabled(available);
        }
    }

    private void setBusy(boolean value) {
        busy = value;
        for (Button b : buttons) { b.setEnabled(!value); b.setAlpha(value ? .55f : 1f); }
    }

    private void execute(final String action) {
        if (busy) return;
        setBusy(true);
        final int id = ++serial;
        pending = id;
        Intent callback = new Intent(this, ResultReceiver.class);
        callback.putExtra("request", action); callback.putExtra("request_id", id);
        PendingIntent result = PendingIntent.getBroadcast(this, id, callback, PendingIntent.FLAG_ONE_SHOT | 0x02000000);
        Intent run = new Intent("com.termux.RUN_COMMAND");
        run.setClassName("com.termux", "com.termux.app.RunCommandService");
        run.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/desktop");
        String[] args = action.equals("force-stop")
            ? new String[]{"force-stop", "--confirmed", "--session", state.optString("session"), "--json"}
            : new String[]{action, "--json"};
        run.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", args);
        run.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home");
        run.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
        run.putExtra("com.termux.RUN_COMMAND_PENDING_INTENT", result);
        try { startService(run); }
        catch (Exception e) { setBusy(false); subtitle.setText("\u65e0\u6cd5\u8fde\u63a5\u684c\u9762\u7ba1\u7406\u670d\u52a1"); }
        handler.postDelayed(new Runnable() {
            public void run() {
                if (pending == id && busy) {
                    setBusy(false);
                    subtitle.setText("\u8fde\u63a5\u8d85\u65f6\uff0c\u8bf7\u91cd\u65b0\u6253\u5f00\u7ba1\u7406");
                }
            }
        }, 55000);
    }

    void received(String action, int id, Bundle result) {
        if (id != pending) return;
        setBusy(false);
        try {
            if (result == null || result.getInt("exitCode", -1) != 0) {
                subtitle.setText("\u64cd\u4f5c\u672a\u5b8c\u6210\uff0c\u8bf7\u68c0\u67e5\u684c\u9762\u72b6\u6001");
                return;
            }
            JSONObject data = new JSONObject(result.getString("stdout"));
            if (pendingDesktopStart && !action.equals("start") && !action.equals("stop") && !action.equals("force-stop")) {
                pendingDesktopStart = false;
                renderMain();
                execute("start");
                return;
            }
            if (action.equals("events")) { renderEvents(data); return; }
            state = data;
            showState();
            if (action.equals("start") || action.equals("stop")) {
                Intent x11 = new Intent();
                x11.setClassName("com.termux.x11", "com.termux.x11.MainActivity");
                startActivity(x11); finish();
            }
        } catch (Exception e) { subtitle.setText("\u72b6\u6001\u6682\u4e0d\u53ef\u7528\uff0c\u8bf7\u91cd\u65b0\u6253\u5f00\u7ba1\u7406"); }
    }

    private String eventName(String name) {
        if (name.equals("desktop-running")) return "\u684c\u9762\u5df2\u542f\u52a8";
        if (name.equals("desktop-start-requested")) return "\u6b63\u5728\u542f\u52a8\u684c\u9762";
        if (name.equals("normal-stop-begun")) return "\u5f00\u59cb\u6b63\u5e38\u7ed3\u675f";
        if (name.equals("normal-stop-cancelled")) return "\u5df2\u53d6\u6d88\u7ed3\u675f";
        if (name.equals("desktop-stopped")) return "\u684c\u9762\u5df2\u7ed3\u675f";
        if (name.startsWith("orphan-helper")) return "\u5df2\u5904\u7406\u5f02\u5e38\u8f85\u52a9\u8fdb\u7a0b";
        if (name.equals("sustained-cpu-observed")) return "\u8bb0\u5f55\u9ad8\u8d1f\u8f7d\uff0c\u6d3b\u52a8\u5e94\u7528\u4fdd\u7559";
        if (name.equals("desktop-session-ended-unexpectedly")) return "\u4f1a\u8bdd\u610f\u5916\u7ed3\u675f\uff0c\u9700\u8981\u68c0\u67e5";
        return "\u684c\u9762\u72b6\u6001\u5df2\u66f4\u65b0";
    }

    private void renderEvents(JSONObject data) throws Exception {
        base("\u68c0\u67e5\u8bb0\u5f55");
        subtitle.setText("\u6bcf 60 \u79d2\u68c0\u67e5\u4e00\u6b21\uff0c\u4ec5\u5904\u7406\u5df2\u786e\u8ba4\u7684\u6b8b\u7559\u8f85\u52a9\u8fdb\u7a0b");
        ScrollView scroll = new ScrollView(this);
        LinearLayout rows = new LinearLayout(this); rows.setOrientation(LinearLayout.VERTICAL);
        JSONArray events = data.optJSONArray("events");
        if (events != null) for (int i = Math.max(0, events.length()-8); i < events.length(); i++) {
            JSONObject event = new JSONObject(events.getString(i));
            String time = event.optString("time");
            TextView row = text((time.length() >= 16 ? time.substring(11,16) : "") + "  " + eventName(event.optString("event")), 15, TEXT, false);
            row.setPadding(0, dp(8), 0, dp(8)); rows.addView(row, new LinearLayout.LayoutParams(-1,-2));
        }
        scroll.addView(rows); actions.addView(scroll, new LinearLayout.LayoutParams(-1,dp(245)));
        button("\u8fd4\u56de\u7ba1\u7406", "back", 1);
    }
}
