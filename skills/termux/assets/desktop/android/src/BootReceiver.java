package com.scisaga.tabletdesktop;

import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;

public final class BootReceiver extends BroadcastReceiver {
    static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences("boot-recovery", Context.MODE_PRIVATE);
    }

    static boolean enabled(Context context) {
        return preferences(context).getBoolean("enabled", false);
    }

    static void configure(Context context, boolean enabled) {
        context.getPackageManager().setComponentEnabledSetting(
            new ComponentName(context, BootReceiver.class),
            enabled ? PackageManager.COMPONENT_ENABLED_STATE_ENABLED
                    : PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP);
        preferences(context).edit().putBoolean("enabled", enabled).apply();
    }

    @Override public void onReceive(Context context, Intent intent) {
        if (intent == null || !Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())
                || !enabled(context)) return;
        preferences(context).edit().putString("status", "pending")
            .putLong("time", System.currentTimeMillis()).apply();
        Intent callback = new Intent(context, BootResultReceiver.class);
        PendingIntent result = PendingIntent.getBroadcast(context, 0, callback,
            PendingIntent.FLAG_ONE_SHOT | 0x02000000);
        Intent run = new Intent("com.termux.RUN_COMMAND");
        run.setClassName("com.termux", "com.termux.app.RunCommandService");
        run.putExtra("com.termux.RUN_COMMAND_PATH",
            "/data/data/com.termux/files/usr/bin/tablet-boot-services");
        run.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", new String[0]);
        run.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home");
        run.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
        run.putExtra("com.termux.RUN_COMMAND_PENDING_INTENT", result);
        try {
            context.startService(run);
        } catch (Exception e) {
            result.cancel();
            preferences(context).edit().putString("status", "failed").apply();
        }
    }
}
