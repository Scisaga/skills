package com.scisaga.tabletdesktop;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;

public final class BootResultReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        Bundle result = intent == null ? null : intent.getBundleExtra("result");
        int exitCode = result == null ? -1 : result.getInt("exitCode", -1);
        BootReceiver.preferences(context).edit()
            .putString("status", exitCode == 0 ? "ok" : "failed")
            .putInt("exitCode", exitCode).putLong("time", System.currentTimeMillis()).apply();
    }
}
