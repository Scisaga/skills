package io.github.scisaga.termuxbluetoothbridge;

import android.Manifest;
import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.text.method.ScrollingMovementMethod;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

public final class MainActivity extends Activity {
    private static final int REQUEST_PERMISSIONS = 1001;
    private TextView status;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        acceptProvisioningToken(getIntent());
        createUi();
        refreshStatus();
        if (hasBluetoothPermissions()) {
            startBridge();
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        acceptProvisioningToken(intent);
        refreshStatus();
        if (hasBluetoothPermissions()) {
            startBridge();
        }
    }

    private void acceptProvisioningToken(Intent intent) {
        if (intent == null) {
            return;
        }
        String incoming = intent.getStringExtra(BridgeConfig.TOKEN_EXTRA);
        if (incoming != null && !BridgeConfig.importTokenIfAllowed(this, incoming)) {
            Toast.makeText(this, "Bridge token was not changed", Toast.LENGTH_LONG).show();
        }
    }

    private void createUi() {
        int padding = (int) (20 * getResources().getDisplayMetrics().density);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(padding, padding, padding, padding);

        TextView title = new TextView(this);
        title.setText("Termux Bluetooth Bridge");
        title.setTextSize(24);
        layout.addView(title);

        status = new TextView(this);
        status.setTextSize(15);
        status.setPadding(0, padding / 2, 0, padding / 2);
        status.setMovementMethod(new ScrollingMovementMethod());
        layout.addView(status, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));

        Button grant = new Button(this);
        grant.setText("Grant Nearby devices permission");
        grant.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                requestBridgePermissions();
            }
        });
        layout.addView(grant);

        Button start = new Button(this);
        start.setText("Start local bridge");
        start.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                if (hasBluetoothPermissions()) {
                    startBridge();
                } else {
                    requestBridgePermissions();
                }
                refreshStatus();
            }
        });
        layout.addView(start);

        Button copy = new Button(this);
        copy.setText("Copy bridge token");
        copy.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                String token = BridgeConfig.getOrCreateToken(MainActivity.this);
                ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                clipboard.setPrimaryClip(ClipData.newPlainText("Termux Bluetooth Bridge token", token));
                Toast.makeText(MainActivity.this, "Token copied", Toast.LENGTH_SHORT).show();
            }
        });
        layout.addView(copy);

        setContentView(layout);
    }

    private void requestBridgePermissions() {
        List<String> missing = new ArrayList<String>();
        if (Build.VERSION.SDK_INT >= 31) {
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
                missing.add(Manifest.permission.BLUETOOTH_SCAN);
            }
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                missing.add(Manifest.permission.BLUETOOTH_CONNECT);
            }
        } else if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            missing.add(Manifest.permission.ACCESS_FINE_LOCATION);
        }
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            missing.add(Manifest.permission.POST_NOTIFICATIONS);
        }
        if (missing.isEmpty()) {
            startBridge();
            refreshStatus();
            return;
        }
        requestPermissions(missing.toArray(new String[missing.size()]), REQUEST_PERMISSIONS);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == REQUEST_PERMISSIONS) {
            if (hasBluetoothPermissions()) {
                startBridge();
            }
            refreshStatus();
        }
    }

    private boolean hasBluetoothPermissions() {
        if (Build.VERSION.SDK_INT >= 31) {
            return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
                    && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
        }
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void startBridge() {
        Intent service = new Intent(this, BluetoothBridgeService.class);
        if (Build.VERSION.SDK_INT >= 26) {
            startForegroundService(service);
        } else {
            startService(service);
        }
    }

    private void refreshStatus() {
        String token = BridgeConfig.getOrCreateToken(this);
        String text = "This is an independent, local-only companion for Termux.\n\n"
                + "Nearby devices permission: " + (hasBluetoothPermissions() ? "granted" : "missing") + "\n"
                + "Loopback endpoint: http://127.0.0.1:" + BridgeConfig.PORT + "\n"
                + "Token fingerprint: " + BridgeConfig.fingerprint(token) + "\n\n"
                + "The bridge can report adapter status, list bonded devices, and perform a bounded BLE scan. "
                + "It cannot silently enable Bluetooth or generically connect every Bluetooth profile.";
        status.setText(text);
    }
}
