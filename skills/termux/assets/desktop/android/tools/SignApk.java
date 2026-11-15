import com.android.apksig.ApkSigner;
import com.android.apksig.ApkVerifier;
import java.io.File;
import java.io.FileInputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;
import java.util.Collections;

public final class SignApk {
    public static void main(String[] args) throws Exception {
        char[] password = new String(Files.readAllBytes(Paths.get(args[1])), "UTF-8").trim().toCharArray();
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (FileInputStream f = new FileInputStream(args[0])) { store.load(f, password); }
        PrivateKey key = (PrivateKey) store.getKey("desktop", password);
        X509Certificate cert = (X509Certificate) store.getCertificate("desktop");
        ApkSigner.SignerConfig signer = new ApkSigner.SignerConfig.Builder("desktop", key, Collections.singletonList(cert)).build();
        new ApkSigner.Builder(Collections.singletonList(signer)).setInputApk(new File(args[2])).setOutputApk(new File(args[3]))
            .setMinSdkVersion(26).setV1SigningEnabled(true).setV2SigningEnabled(true).setV3SigningEnabled(true).build().sign();
        if (!new ApkVerifier.Builder(new File(args[3])).build().verify().isVerified()) throw new IllegalStateException("Signature verification failed");
    }
}
