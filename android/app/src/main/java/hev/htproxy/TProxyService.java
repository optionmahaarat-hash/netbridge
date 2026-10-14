package hev.htproxy;

/** JNI entry points of hev-socks5-tunnel (class name is the library's default: hev/htproxy/TProxyService). */
public class TProxyService {
    static { System.loadLibrary("hev-socks5-tunnel"); }
    public static native void TProxyStartService(String configPath, int fd);
    public static native void TProxyStopService();
    public static native long[] TProxyGetStats();
}
