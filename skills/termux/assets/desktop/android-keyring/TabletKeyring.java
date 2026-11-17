import java.io.File;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.*;
import java.security.spec.AlgorithmParameterSpec;
import java.util.*;
import java.util.concurrent.TimeUnit;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;

/** One-shot Android Keystore bridge. No action returns the keyring password. */
public final class TabletKeyring {
    private static final String ALIAS = "scisaga.tablet-desktop.gnome-keyring.v1";
    private static final byte[] MAGIC = new byte[] {84, 68, 75, 82, 1, 0};
    private static final byte[] AAD = ALIAS.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    private static final Set<java.nio.file.attribute.PosixFilePermission> PRIVATE_FILE =
        PosixFilePermissions.fromString("rw-------");
    private static final Set<java.nio.file.attribute.PosixFilePermission> PRIVATE_DIR =
        PosixFilePermissions.fromString("rwx------");

    private static KeyStore store() throws Exception {
        // app_process does not perform an Android application's provider setup.
        Class.forName("android.security.keystore2.AndroidKeyStoreProvider")
            .getMethod("install").invoke(null);
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        return store;
    }

    private static SecretKey createKey(String alias) throws Exception {
        Class<?> type = Class.forName("android.security.keystore.KeyGenParameterSpec$Builder");
        Object b = type.getConstructor(String.class, int.class).newInstance(alias, 3);
        type.getMethod("setBlockModes", String[].class).invoke(b, (Object)new String[] {"GCM"});
        type.getMethod("setEncryptionPaddings", String[].class).invoke(b, (Object)new String[] {"NoPadding"});
        type.getMethod("setKeySize", int.class).invoke(b, 256);
        type.getMethod("setUnlockedDeviceRequired", boolean.class).invoke(b, true);
        KeyGenerator generator = KeyGenerator.getInstance("AES", "AndroidKeyStore");
        generator.init((AlgorithmParameterSpec)type.getMethod("build").invoke(b));
        SecretKey key = generator.generateKey();
        requireHardware(key);
        return key;
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static int requireHardware(SecretKey key) throws Exception {
        Class<?> type = Class.forName("android.security.keystore.KeyInfo");
        Object info = SecretKeyFactory.getInstance("AES", "AndroidKeyStore").getKeySpec(key, (Class)type);
        int level = ((Number)type.getMethod("getSecurityLevel").invoke(info)).intValue();
        if (key.getEncoded() != null || (level != 1 && level != 2))
            throw new SecurityException("Hardware-backed non-exportable key required");
        return level;
    }

    private static void checkPrivate(Path path, boolean directory) throws Exception {
        if (Files.isSymbolicLink(path) || !Files.getPosixFilePermissions(path).equals(directory ? PRIVATE_DIR : PRIVATE_FILE))
            throw new SecurityException("Private path permissions required");
    }

    private static Path directory() throws Exception {
        String home = System.getenv("HOME");
        if (home == null || !home.startsWith("/home/"))
            throw new SecurityException("Run inside the desktop guest");
        Path dir = Paths.get(home, ".local/share/tablet-desktop/android-keyring");
        for (Path p = dir; p != null; p = p.getParent())
            if (Files.isSymbolicLink(p)) throw new SecurityException("Symlink state paths refused");
        return dir;
    }

    private static byte[] encrypt(SecretKey key, byte[] plain) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key);
        cipher.updateAAD(AAD);
        byte[] encrypted = cipher.doFinal(plain);
        return ByteBuffer.allocate(MAGIC.length + 12 + encrypted.length)
            .put(MAGIC).put(cipher.getIV()).put(encrypted).array();
    }

    private static byte[] decrypt(SecretKey key, byte[] sealed) throws Exception {
        if (sealed.length != MAGIC.length + 12 + 44 + 16 ||
            !Arrays.equals(MAGIC, Arrays.copyOfRange(sealed, 0, MAGIC.length)))
            throw new SecurityException("Invalid sealed state");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(128, Arrays.copyOfRange(sealed, MAGIC.length, MAGIC.length + 12)));
        cipher.updateAAD(AAD);
        return cipher.doFinal(Arrays.copyOfRange(sealed, MAGIC.length + 12, sealed.length));
    }

    private static void initialize(KeyStore store, Path dir) throws Exception {
        Path sealed = dir.resolve("master.sealed");
        if (Files.exists(sealed)) return;
        Path keyrings = Paths.get(System.getenv("HOME"), ".local/share/keyrings");
        if (Files.exists(keyrings)) {
            try (DirectoryStream<Path> files = Files.newDirectoryStream(keyrings, "*.keyring")) {
                if (files.iterator().hasNext()) throw new SecurityException("Existing keyrings require a separate migration");
            }
        }
        if (store.containsAlias(ALIAS)) throw new SecurityException("Existing Android key has no sealed state; restore the state first");
        Files.createDirectories(dir, PosixFilePermissions.asFileAttribute(PRIVATE_DIR));
        checkPrivate(dir, true);
        byte[] random = new byte[32];
        new SecureRandom().nextBytes(random);
        byte[] password = Base64.getEncoder().encode(random);
        Arrays.fill(random, (byte)0);
        Path temp = null;
        try {
            SecretKey key = createKey(ALIAS);
            byte[] encrypted = encrypt(key, password);
            temp = Files.createTempFile(dir, ".sealed-", ".tmp", PosixFilePermissions.asFileAttribute(PRIVATE_FILE));
            try (FileChannel channel = FileChannel.open(temp, StandardOpenOption.WRITE)) {
                ByteBuffer buffer = ByteBuffer.wrap(encrypted);
                while (buffer.hasRemaining()) channel.write(buffer);
                channel.force(true);
            }
            Files.move(temp, sealed, StandardCopyOption.ATOMIC_MOVE);
            temp = null;
        } finally {
            Arrays.fill(password, (byte)0);
            if (temp != null) Files.deleteIfExists(temp);
        }
    }

    private static int unlock(KeyStore store, Path dir) throws Exception {
        Path sealed = dir.resolve("master.sealed");
        checkPrivate(dir, true);
        checkPrivate(sealed, false);
        if (!store.containsAlias(ALIAS)) throw new SecurityException("Android key is unavailable; never recreate it over saved credentials");
        SecretKey key = (SecretKey)store.getKey(ALIAS, null);
        int level = requireHardware(key);
        byte[] password = decrypt(key, Files.readAllBytes(sealed));
        Process child = null;
        try {
            String control = System.getenv("GNOME_KEYRING_CONTROL");
            if (control == null || !control.startsWith(System.getenv("HOME") + "/.cache/tablet-desktop/keyring-"))
                throw new SecurityException("Private session control directory required");
            child = new ProcessBuilder("/usr/bin/gnome-keyring-daemon", "--unlock", "--components=secrets", "--daemonize", "--control-directory=" + control)
                .redirectOutput(new File("/dev/null")).redirectError(new File("/dev/null")).start();
            try (OutputStream input = child.getOutputStream()) { input.write(password); }
            if (!child.waitFor(15, TimeUnit.SECONDS)) throw new SecurityException("Keyring daemon timed out");
            if (child.exitValue() != 0) throw new SecurityException("Keyring daemon failed");
            return level;
        } finally {
            Arrays.fill(password, (byte)0);
            if (child != null && child.isAlive()) child.destroy();
        }
    }

    private static int probe(KeyStore store) throws Exception {
        String alias = ALIAS + ".probe." + UUID.randomUUID();
        try {
            SecretKey key = createKey(alias);
            byte[] test = new byte[44];
            new SecureRandom().nextBytes(test);
            if (!Arrays.equals(test, decrypt(key, encrypt(key, test))))
                throw new SecurityException("Keystore round trip failed");
            Arrays.fill(test, (byte)0);
            return requireHardware(key);
        } finally {
            if (store.containsAlias(alias)) store.deleteEntry(alias);
        }
    }

    public static void main(String[] args) {
        try {
            if (args.length != 1 || !Arrays.asList("probe", "initialize", "unlock", "info").contains(args[0]))
                throw new IllegalArgumentException("Expected probe, initialize, unlock or info");
            KeyStore store = store();
            int level;
            if (args[0].equals("probe")) level = probe(store);
            else if (args[0].equals("info")) level = requireHardware((SecretKey)store.getKey(ALIAS, null));
            else {
                Path dir = directory();
                if (args[0].equals("initialize")) initialize(store, dir);
                level = unlock(store, dir);
            }
            System.out.println("{\"ok\":true,\"security_level\":" + level + ",\"non_exportable\":true}");
        } catch (Throwable error) {
            while (error.getCause() != null) error = error.getCause();
            // Do not print exception messages, child output, passwords or stack traces.
            System.out.println("{\"ok\":false,\"error\":\"" + error.getClass().getSimpleName() + "\"}");
            System.exit(1);
        }
    }
}
