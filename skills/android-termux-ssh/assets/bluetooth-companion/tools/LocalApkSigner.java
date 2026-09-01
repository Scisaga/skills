import com.android.apksig.ApkSigner;
import com.android.apksig.ApkVerifier;

import java.io.File;
import java.io.FileInputStream;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;
import java.util.Collections;
import java.util.List;

public final class LocalApkSigner {
    private LocalApkSigner() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            throw new IllegalArgumentException("usage: LocalApkSigner sign|verify ...");
        }
        if ("sign".equals(args[0])) {
            sign(args);
        } else if ("verify".equals(args[0])) {
            verify(args[1]);
        } else {
            throw new IllegalArgumentException("unknown action: " + args[0]);
        }
    }

    private static void sign(String[] args) throws Exception {
        if (args.length != 7) {
            throw new IllegalArgumentException(
                    "sign requires: input.apk output.apk keystore password alias minSdk");
        }
        char[] password = args[4].toCharArray();
        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        FileInputStream stream = new FileInputStream(args[3]);
        try {
            keyStore.load(stream, password);
        } finally {
            stream.close();
        }
        PrivateKey privateKey = (PrivateKey) keyStore.getKey(args[5], password);
        X509Certificate certificate = (X509Certificate) keyStore.getCertificate(args[5]);
        if (privateKey == null || certificate == null) {
            throw new IllegalStateException("signing key or certificate is missing");
        }
        List<X509Certificate> certificates = Collections.singletonList(certificate);
        ApkSigner.SignerConfig signer = new ApkSigner.SignerConfig.Builder(
                "TERMUX-BRIDGE", privateKey, certificates).build();
        new ApkSigner.Builder(Collections.singletonList(signer))
                .setInputApk(new File(args[1]))
                .setOutputApk(new File(args[2]))
                .setMinSdkVersion(Integer.parseInt(args[6]))
                .setV1SigningEnabled(true)
                .setV2SigningEnabled(true)
                .setV3SigningEnabled(true)
                .build()
                .sign();
    }

    private static void verify(String apk) throws Exception {
        ApkVerifier.Result result = new ApkVerifier.Builder(new File(apk)).build().verify();
        if (!result.isVerified()) {
            for (Object error : result.getErrors()) {
                System.err.println(error);
            }
            throw new IllegalStateException("APK signature verification failed");
        }
        System.out.println("APK signature verified: v1=" + result.isVerifiedUsingV1Scheme()
                + " v2=" + result.isVerifiedUsingV2Scheme()
                + " v3=" + result.isVerifiedUsingV3Scheme());
    }
}
