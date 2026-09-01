package io.github.scisaga.termuxbluetoothbridge;

import android.content.Context;
import android.content.SharedPreferences;

import java.security.MessageDigest;
import java.security.SecureRandom;

final class BridgeConfig {
    static final String PREFS = "bridge";
    static final String TOKEN_KEY = "token";
    static final String TOKEN_EXTRA = "bridge_token";
    static final int PORT = 18765;

    private BridgeConfig() {}

    static synchronized String getOrCreateToken(Context context) {
        SharedPreferences preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String current = preferences.getString(TOKEN_KEY, null);
        if (isValidToken(current)) {
            return current;
        }

        byte[] random = new byte[32];
        new SecureRandom().nextBytes(random);
        String generated = hex(random);
        preferences.edit().putString(TOKEN_KEY, generated).apply();
        return generated;
    }

    static synchronized boolean importTokenIfAllowed(Context context, String candidate) {
        if (!isValidToken(candidate)) {
            return false;
        }
        SharedPreferences preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String current = preferences.getString(TOKEN_KEY, null);
        if (current == null || current.equals(candidate)) {
            preferences.edit().putString(TOKEN_KEY, candidate).commit();
            return true;
        }
        return false;
    }

    static boolean isValidToken(String value) {
        return value != null && value.matches("[0-9a-fA-F]{64}");
    }

    static String fingerprint(String token) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            String full = hex(digest.digest(token.getBytes("UTF-8")));
            return full.substring(0, 16);
        } catch (Exception error) {
            return "unavailable";
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            result.append(String.format("%02x", value & 0xff));
        }
        return result.toString();
    }
}
