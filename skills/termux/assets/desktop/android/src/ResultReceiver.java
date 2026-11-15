package com.scisaga.tabletdesktop;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;

public final class ResultReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        ManagerActivity a = ManagerActivity.active;
        if (a != null) a.received(intent.getStringExtra("request"), intent.getIntExtra("request_id", 0), intent.getBundleExtra("result"));
    }
}
