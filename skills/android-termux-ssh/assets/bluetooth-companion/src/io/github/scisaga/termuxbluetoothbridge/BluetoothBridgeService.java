package io.github.scisaga.termuxbluetoothbridge;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.IBinder;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class BluetoothBridgeService extends Service {
    private static final String CHANNEL_ID = "bridge";
    private static final int NOTIFICATION_ID = 18765;
    private final ExecutorService clients = Executors.newCachedThreadPool();
    private final AtomicBoolean scanInProgress = new AtomicBoolean(false);
    private volatile ServerSocket server;
    private volatile boolean stopping;
    private String token;

    @Override
    public void onCreate() {
        super.onCreate();
        if (!hasScanPermission() || !hasConnectPermission()) {
            stopSelf();
            return;
        }
        token = BridgeConfig.getOrCreateToken(this);
        startForeground(NOTIFICATION_ID, createNotification());
        startLoopbackServer();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        stopping = true;
        ServerSocket current = server;
        if (current != null) {
            try {
                current.close();
            } catch (Exception ignored) {
            }
        }
        clients.shutdownNow();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private Notification createNotification() {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, "Termux Bluetooth Bridge", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Local authenticated Bluetooth access for Termux");
            manager.createNotificationChannel(channel);
        }
        Intent open = new Intent(this, MainActivity.class);
        int pendingFlags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) {
            pendingFlags |= PendingIntent.FLAG_IMMUTABLE;
        }
        PendingIntent pending = PendingIntent.getActivity(this, 0, open, pendingFlags);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setContentTitle("Termux Bluetooth Bridge")
                .setContentText("Local bridge active on 127.0.0.1:" + BridgeConfig.PORT)
                .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
                .setContentIntent(pending)
                .setOngoing(true)
                .build();
    }

    private void startLoopbackServer() {
        Thread acceptThread = new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    ServerSocket listening = new ServerSocket();
                    listening.setReuseAddress(true);
                    listening.bind(new InetSocketAddress(
                            InetAddress.getByName("127.0.0.1"), BridgeConfig.PORT), 16);
                    server = listening;
                    while (!stopping) {
                        final Socket socket = listening.accept();
                        clients.execute(new Runnable() {
                            @Override
                            public void run() {
                                handle(socket);
                            }
                        });
                    }
                } catch (Exception error) {
                    if (!stopping) {
                        stopSelf();
                    }
                }
            }
        }, "bluetooth-bridge-accept");
        acceptThread.start();
    }

    private void handle(Socket socket) {
        try {
            socket.setSoTimeout(35000);
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(socket.getInputStream(), StandardCharsets.US_ASCII));
            String first = reader.readLine();
            if (first == null || first.length() > 2048) {
                respond(socket, 400, "{\"error\":\"bad request\"}");
                return;
            }
            String[] request = first.split(" ");
            if (request.length != 3) {
                respond(socket, 400, "{\"error\":\"bad request line\"}");
                return;
            }
            Map<String, String> headers = new HashMap<String, String>();
            int headerBytes = 0;
            while (true) {
                String line = reader.readLine();
                if (line == null || line.length() == 0) {
                    break;
                }
                headerBytes += line.length();
                if (headerBytes > 8192) {
                    respond(socket, 431, "{\"error\":\"headers too large\"}");
                    return;
                }
                int colon = line.indexOf(':');
                if (colon > 0) {
                    headers.put(line.substring(0, colon).trim().toLowerCase(Locale.ROOT),
                            line.substring(colon + 1).trim());
                }
            }
            if (!("Bearer " + token).equals(headers.get("authorization"))) {
                respond(socket, 401, "{\"error\":\"unauthorized\"}");
                return;
            }

            String method = request[0];
            String target = request[1];
            if ("GET".equals(method) && "/v1/status".equals(target)) {
                respond(socket, 200, statusJson());
            } else if ("GET".equals(method) && "/v1/bonded".equals(target)) {
                respond(socket, 200, bondedJson());
            } else if ("POST".equals(method) && target.startsWith("/v1/ble/scan")) {
                int seconds = parseSeconds(target);
                ScanResponse scan = scanJson(seconds);
                respond(socket, scan.code, scan.json);
            } else {
                respond(socket, 404, "{\"error\":\"not found\"}");
            }
        } catch (Exception ignored) {
            try {
                respond(socket, 500, "{\"error\":\"internal error\"}");
            } catch (Exception ignoredAgain) {
            }
        } finally {
            try {
                socket.close();
            } catch (Exception ignored) {
            }
        }
    }

    private String statusJson() {
        boolean scanPermission = hasScanPermission();
        boolean connectPermission = hasConnectPermission();
        BluetoothAdapter adapter = adapter();
        String state = "unavailable";
        if (adapter != null && connectPermission) {
            try {
                state = adapterState(adapter.getState());
            } catch (SecurityException error) {
                state = "permission-denied";
            }
        }
        return "{\"bridgeVersion\":\"0.1.2\",\"listen\":\"127.0.0.1:"
                + BridgeConfig.PORT + "\",\"bluetoothAvailable\":" + (adapter != null)
                + ",\"adapterState\":\"" + state + "\",\"scanPermission\":" + scanPermission
                + ",\"connectPermission\":" + connectPermission + "}";
    }

    private String bondedJson() {
        if (!hasConnectPermission()) {
            return "{\"error\":\"BLUETOOTH_CONNECT permission is missing\"}";
        }
        BluetoothAdapter adapter = adapter();
        if (adapter == null) {
            return "{\"devices\":[]}";
        }
        try {
            Set<BluetoothDevice> bonded = adapter.getBondedDevices();
            List<BluetoothDevice> devices = new ArrayList<BluetoothDevice>(bonded);
            Collections.sort(devices, new Comparator<BluetoothDevice>() {
                @Override
                public int compare(BluetoothDevice left, BluetoothDevice right) {
                    return safeAddress(left).compareTo(safeAddress(right));
                }
            });
            StringBuilder json = new StringBuilder("{\"devices\":[");
            boolean first = true;
            for (BluetoothDevice device : devices) {
                if (!first) {
                    json.append(',');
                }
                first = false;
                json.append(deviceJson(device, null, null));
            }
            return json.append("]}").toString();
        } catch (SecurityException error) {
            return "{\"error\":\"BLUETOOTH_CONNECT permission was denied\"}";
        }
    }

    private ScanResponse scanJson(int seconds) {
        if (!hasScanPermission() || !hasConnectPermission()) {
            return new ScanResponse(403,
                    "{\"error\":\"Nearby devices scan/connect permission is missing\"}");
        }
        if (!scanInProgress.compareAndSet(false, true)) {
            return new ScanResponse(409, "{\"error\":\"a BLE scan is already running\"}");
        }
        try {
            BluetoothAdapter adapter = adapter();
            if (adapter == null || adapter.getState() != BluetoothAdapter.STATE_ON) {
                return new ScanResponse(409, "{\"error\":\"Bluetooth is unavailable or disabled\"}");
            }
            final BluetoothLeScanner scanner = adapter.getBluetoothLeScanner();
            if (scanner == null) {
                return new ScanResponse(409, "{\"error\":\"BLE scanner is unavailable\"}");
            }
            final ConcurrentHashMap<String, ScanResult> found = new ConcurrentHashMap<String, ScanResult>();
            final CountDownLatch finished = new CountDownLatch(1);
            ScanCallback callback = new ScanCallback() {
                @Override
                public void onScanResult(int callbackType, ScanResult result) {
                    found.put(safeAddress(result.getDevice()), result);
                }

                @Override
                public void onBatchScanResults(List<ScanResult> results) {
                    for (ScanResult result : results) {
                        found.put(safeAddress(result.getDevice()), result);
                    }
                }

                @Override
                public void onScanFailed(int errorCode) {
                    finished.countDown();
                }
            };
            scanner.startScan(callback);
            finished.await(seconds, TimeUnit.SECONDS);
            scanner.stopScan(callback);

            List<ScanResult> results = new ArrayList<ScanResult>(found.values());
            Collections.sort(results, new Comparator<ScanResult>() {
                @Override
                public int compare(ScanResult left, ScanResult right) {
                    return safeAddress(left.getDevice()).compareTo(safeAddress(right.getDevice()));
                }
            });
            StringBuilder json = new StringBuilder();
            json.append("{\"seconds\":").append(seconds).append(",\"devices\":[");
            boolean first = true;
            for (ScanResult result : results) {
                if (!first) {
                    json.append(',');
                }
                first = false;
                json.append(deviceJson(result.getDevice(), result.getRssi(), result.isConnectable()));
            }
            json.append("]}");
            return new ScanResponse(200, json.toString());
        } catch (SecurityException error) {
            return new ScanResponse(403, "{\"error\":\"Bluetooth permission was denied\"}");
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return new ScanResponse(500, "{\"error\":\"scan interrupted\"}");
        } finally {
            scanInProgress.set(false);
        }
    }

    private BluetoothAdapter adapter() {
        BluetoothManager manager = (BluetoothManager) getSystemService(BLUETOOTH_SERVICE);
        return manager == null ? null : manager.getAdapter();
    }

    private boolean hasScanPermission() {
        return Build.VERSION.SDK_INT < 31
                || checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean hasConnectPermission() {
        return Build.VERSION.SDK_INT < 31
                || checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private static int parseSeconds(String target) {
        int marker = target.indexOf("seconds=");
        if (marker < 0) {
            return 8;
        }
        int start = marker + "seconds=".length();
        int end = target.indexOf('&', start);
        String value = end < 0 ? target.substring(start) : target.substring(start, end);
        try {
            return Math.max(1, Math.min(25, Integer.parseInt(value)));
        } catch (NumberFormatException error) {
            return 8;
        }
    }

    private static String adapterState(int state) {
        switch (state) {
            case BluetoothAdapter.STATE_OFF: return "off";
            case BluetoothAdapter.STATE_TURNING_ON: return "turning-on";
            case BluetoothAdapter.STATE_ON: return "on";
            case BluetoothAdapter.STATE_TURNING_OFF: return "turning-off";
            default: return "unknown";
        }
    }

    private static String deviceJson(BluetoothDevice device, Integer rssi, Boolean connectable) {
        String name = null;
        int type = 0;
        int bond = 0;
        try {
            name = device.getName();
            type = device.getType();
            bond = device.getBondState();
        } catch (SecurityException ignored) {
        }
        StringBuilder json = new StringBuilder();
        json.append("{\"address\":\"").append(escape(safeAddress(device))).append("\"")
                .append(",\"name\":").append(name == null ? "null" : "\"" + escape(name) + "\"")
                .append(",\"type\":").append(type)
                .append(",\"bondState\":").append(bond);
        if (rssi != null) {
            json.append(",\"rssi\":").append(rssi);
        }
        if (connectable != null) {
            json.append(",\"connectable\":").append(connectable);
        }
        return json.append('}').toString();
    }

    private static String safeAddress(BluetoothDevice device) {
        try {
            String address = device.getAddress();
            return address == null ? "unknown" : address;
        } catch (SecurityException error) {
            return "unknown";
        }
    }

    private static String escape(String value) {
        StringBuilder escaped = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '\\': escaped.append("\\\\"); break;
                case '"': escaped.append("\\\""); break;
                case '\n': escaped.append("\\n"); break;
                case '\r': escaped.append("\\r"); break;
                case '\t': escaped.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        escaped.append(String.format("\\u%04x", (int) c));
                    } else {
                        escaped.append(c);
                    }
            }
        }
        return escaped.toString();
    }

    private static void respond(Socket socket, int code, String json) throws Exception {
        byte[] body = json.getBytes(StandardCharsets.UTF_8);
        String reason;
        switch (code) {
            case 200: reason = "OK"; break;
            case 400: reason = "Bad Request"; break;
            case 401: reason = "Unauthorized"; break;
            case 403: reason = "Forbidden"; break;
            case 404: reason = "Not Found"; break;
            case 409: reason = "Conflict"; break;
            case 431: reason = "Request Header Fields Too Large"; break;
            default: reason = "Internal Server Error";
        }
        OutputStream output = socket.getOutputStream();
        BufferedWriter headers = new BufferedWriter(new OutputStreamWriter(output, StandardCharsets.US_ASCII));
        headers.write("HTTP/1.1 " + code + " " + reason + "\r\n");
        headers.write("Content-Type: application/json; charset=utf-8\r\n");
        headers.write("Cache-Control: no-store\r\n");
        headers.write("Connection: close\r\n");
        headers.write("Content-Length: " + body.length + "\r\n\r\n");
        headers.flush();
        output.write(body);
        output.flush();
    }

    private static final class ScanResponse {
        final int code;
        final String json;

        ScanResponse(int code, String json) {
            this.code = code;
            this.json = json;
        }
    }
}
