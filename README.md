# NetBridge v0.6

Personal Windows GUI client.

## Added in v0.2
- VLESS URI parsing
- VMess base64 URI parsing
- Trojan URI parsing
- Shadowsocks URI parsing
- Generic subscription import
- Multi-profile management
- Profile validation
- Xray config generation
- Xray process start/stop
- Log polling
- Config file import/export
- Clipboard paste
- Duplicate filtering

## Run

```powershell
py -m pip install -r requirements.txt
py main.py
```

Put the Windows Xray executable at:

```text
cores/xray/xray.exe
```

## v0.3 - Bypass (Fragment + unsafe fingerprint + cipherSuites)
Select a TLS profile -> Bypass button. Modes: Off / Standard / PattNG exact / Custom.
Also: Clean IP field (changes only the connect address, SNI/Host stay), and share-link
params `fm` (finalMask JSON), `cs` (cipherSuites), `fp=unsafe`, Reality (pbk/sid/spx), gRPC.
Needs Xray >= 26.7 for the exact video values (setup.bat downloads the latest). Test button now also runs `xray run -test` on the generated config.

## v0.5 - sing-box JSON import, Bypass all TLS
Import a sing-box JSON (Add or Import file). Non-TLS profiles can be skipped.

## v0.4 - Windows setup
1. Install Python 3.11+ (tick "Add Python to PATH").
2. Double-click setup.bat  (installs PySide6, downloads xray.exe)
3. Double-click run.bat
Also new: Subscription import, Windows System Proxy checkbox, Real delay test, non-blocking log.

## v0.6 - Hiddify-style selection + Skip sites (routing)
**Connection mode** (combo above CONNECT):
- Manual: the profile you select.
- Best now: tests every profile in the current group (real delay, parallel, own temp Xray each), connects to the fastest.
- Auto balancer: one Xray with all profiles in the group (max 30) and a leastPing balancer + observatory, so it keeps using the fastest one live (like Hiddify "Auto").

**Groups**: profiles from a subscription get the subscription host as group; imported files get the file name. Filter with the Group box. "Test all (delay)" fills the ms column, "Sort by delay" orders the list.

**Skip sites (Routing)**: for sites that reject your location (foreign/datacenter IP):
- "Iranian sites go direct" (.ir + geosite:category-ir + geoip:ir)
- your own list (site, URL, IP, CIDR, geosite:xxx, geoip:xx) that skips the tunnel
- "Always use the tunnel" list (wins over the skip list)
- local network direct, ad blocking
Domain matching uses domainStrategy=AsIs on purpose, so a poisoned local DNS answer (fake 10.10.x.x) can never make a blocked site go "direct".
Rules need geoip.dat / geosite.dat next to xray.exe (get_xray.py downloads them).

## v0.6.1 - Sites that reject Iranian IPs
Routing dialog -> "Sites that reject Iranian IPs": list the sites + pick the server they must exit from.
Keep "Iranian sites go direct" OFF for this (that option is the opposite: for Iranian sites that reject foreign IPs).
Button "Check exit IP / country" shows what websites see when you are connected.
If the exit is Cloudflare (Workers configs), sites behind Cloudflare can still see your real country -> use a non-Cloudflare server as the exit for those sites.

## v0.6.2 - Full sing-box JSON import
Import now understands: VLESS (TLS, **Reality**, ws, gRPC, flow), VMess, Trojan, Shadowsocks, **Hysteria2** (+ salamander obfs).
- Reality profiles were wrongly imported as plain TLS before - fixed.
- Shadowsocks entries exported with method "none" and the real `method:password` hidden in base64 are repaired automatically.
- Skipped with a reason in the log: fake/empty servers (0.0.0.0), methods Xray cannot do (aes-256-cfb, chacha20-ietf), and
  profiles with `insecure` TLS: Xray 26.7 removed allowInsecure, so such a server needs its certificate SHA256 (`pcs=` in the share link).
- Duplicates (same server/port/credentials) are skipped; the log shows how many.
- Edit / Export now work for every protocol. Bypass (fragment) is refused for Shadowsocks and Hysteria2 (not TLS-over-TCP).
- "Test all" runs 10 in parallel. For Auto mode, run "Test all" first: it uses the 30 fastest.

## v0.6.3 - Self-signed servers (insecure) work again
Xray 26.7 removed `allowInsecure`. NetBridge now does the TLS/QUIC handshake itself, reads the server certificate SHA256
and pins it (`pinnedPeerCertSha256`). Runs automatically after import; button "Pin certs (self-signed servers)" retries.
Works for Hysteria2 (incl. salamander obfs) and TLS-over-TCP profiles. Needs: python -m pip install aioquic  (setup.bat does it).
First fetch trusts what the network answers once (like SSH first connect); after that the certificate is pinned.

## v0.6.4 - "location unsupported" diagnostics
Button **Full location check**: asks 5 geo services through the tunnel (ip-api, ipwho.is, ipinfo, Cloudflare, country.is) and tells you
if one of them still says Iran, if they disagree (a site using the "wrong" database rejects you), if the exit is a datacenter/VPN IP,
if your real IP leaks, and if the Windows time zone / Persian language can give you away.
Button **Open clean browser**: Chrome/Edge/Brave with its own profile, direct proxy, WebRTC limited to the proxy (no real-IP leak), language en-US.
Use this browser for sites that say "unsupported location", and deny the Location permission for them.

## v0.6.5 - Clean IP scanner
Button **Clean IP scanner (Cloudflare)**: samples random Cloudflare IPs, and for each one does TCP + TLS (with the selected profile's SNI) +
`GET /cdn-cgi/trace` (Host = your domain) over your normal internet, so you see the real latency from YOUR ISP. Works IPs are listed fastest first.
Use one for the selected profile, or spread the best ones over all Cloudflare profiles (sets 'Clean IP' / address_override).
Note: this only chooses the ENTRY IP. The exit of a Workers/Pages config stays Cloudflare.

## v0.6.6 - Service presets + Sanction DNS (Routing window)
* **Add this service's sites**: one click fills "Sites that reject Iranian IPs" with the domains of OpenAI, Claude, Google AI, Spotify or Netflix.
  They leave through the exit server you choose there (it must NOT be Cloudflare/Workers: use your own VPS, e.g. VLESS+Reality).
* **Sanction DNS (Smart DNS)**: for sanctioned sites that Iran does not filter. The listed sites skip the tunnel and are resolved by a
  Smart DNS server (e.g. Shecan 178.22.122.100); that DNS answers with a foreign proxy address. "Test DNS" checks the answer.
  Does not help for sites that block by the exit IP of your tunnel, and the DNS provider must support the site.

## v0.6.7 - Exit scan
Button **Exit scan**: starts every profile in a private Xray, asks a geo service through it (ip-api, then ipwho.is / ipinfo) and lists
country, exit IP, ISP and flags (CLOUDFLARE / datacenter / vpn-list). *.workers.dev and *.pages.dev profiles are skipped by default.
Select a result and press "Use as the exit for Google AI sites": it becomes the Routing exit and the Google AI domains are added.
Typical free workflow: Subscription (import a public list) -> Exit scan -> pick a non-Cloudflare exit in a supported country -> Open clean browser.

## v0.6.8 - NotebookLM / Gemini / AI Studio test inside Exit scan
Exit scan can now also open notebooklm.google.com, gemini.google.com and aistudio.google.com THROUGH each profile and report OK / BLOCKED
(follows redirects; BLOCKED = final URL like ...?location=unsupported, /unsupported-country, or a "not available in your country" page).
Heuristic: a block drawn only by JavaScript is not detected, so confirm in 'Open clean browser'.

## v0.6.9 - Multi-select delete + Convert non-TLS to TLS
* The profile list now supports multi-select (Ctrl/Shift-click, Ctrl+A or **Select all**). **Delete** removes every selected profile (asks first when more than one).
  **Select failed (x)** selects all profiles that failed 'Test all (delay)' so you can delete them in one go.
* **Convert non-TLS to TLS (try)**: for plain vless/vmess/trojan profiles (security none) it looks for a TLS door on the same server:
  the same port and 443, 8443, 2053, 2083, 2087, 2096. A candidate must answer a TLS handshake AND really work in a private Xray.
  Self-signed certificates are pinned automatically. Same port with TLS: the profile is upgraded in place. Another port: a new profile is added.
  A client cannot add TLS to a server that does not offer it (typical for free hosts on a single plain port): those are reported as "not possible".
* Import: non-TLS profiles are now kept by default (a dialog lets you skip them); comment lines such as '#profile-title: ...' are ignored.
* Fixed: deleting the last profile of the list could raise an IndexError.

## v0.6.10
* Exit scan window explains what to do (nothing to type: press Start scan, look for a non-Cloudflare line with OK), and has
  **Copy visible results**, **Copy config link of selected** and Ctrl+C.
* **Select non-TLS (plain) profiles** selects every plain profile of the current group (then Delete). After 'Convert non-TLS to TLS',
  plain profiles whose TLS twin is already in the list are just redundant.

## v0.6.11 - port conflicts + failed-start detection
* Cause of "Failed to start ... listen tcp 127.0.0.1:10808 ... Only one usage of each socket address": another program (v2rayN, MLM VPN,
  an old NetBridge window ...) already listens on 10808/10809. Before, NetBridge still showed "running" and pointed the Windows proxy at
  the OTHER program, so your routing / pinned exit was never used.
* Now: NetBridge picks the first free port pair (10808/10809, then 10818/10819 ...), says which program holds the default ports,
  uses the chosen port for the Windows proxy, Open clean browser, Full location check, delay test and subscription download.
* If Xray exits right after start (any reason) the window resets to CONNECT, the Windows proxy is switched OFF and the reason is shown.
* Fixed: the exit message of an OLD Xray process could land in the queue of the NEW one.
* Exit scan: pages that cannot be loaded are shown as TIMEOUT / TLS-ERR / ERR instead of '?'.

## Icon and branding
- `assets/source/logo-source.png` is the original artwork. `python tools/make_icons.py` (needs `pip install -r tools/requirements-dev.txt`)
  rebuilds `assets/logo.png`, `assets/mark.png`, `assets/icons/netbridge-<size>.png` and `assets/netbridge.ico`.
  Small sizes (16-96 px) use the symbol only; 128/256 px use the full logo.
- Where it appears: window + dialogs + taskbar/Alt-Tab (`app/ui/icon.py`, `main.py`; Windows AppUserModelID `AppBaz.NetBridge`),
  header of the profile list, Help > About NetBridge (`app/ui/about_dialog.py`).
- `create_shortcut.bat` puts a NetBridge shortcut on the Desktop (icon, no console window; uses pythonw).
- The version number lives in `app/version.py`.
