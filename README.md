# Herspers-Minecraft

Desktop Minecraft clients for **Windows 10/11 x64 PCs**, with older Java Edition packages also available for **Apple Silicon / Intel Macs**.

## Herps Launcher development

**Start here:** [Install, use, or integrate Herps Launcher](docs/HERPS-QUICKSTART.md).

The shared **Herps Launcher 0.1.0** desktop application adds pre-launch profiles, Horizon mod imports and native rebuilds, shader selection, Tailscale favorites, game logs and rollback tools for the Java Edition packages. See [launcher setup and verification limits](docs/HERPS-LAUNCHER.md) and [native app builds/downloads](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41571739445). Its Windows/macOS packages are separate from the existing game downloads below. Game rendering, gameplay and two-PC multiplayer require separate validation with the user's game files.

The new **Herspers Bedrock 0.3.0** target uses Cinnabar's native Rust game client and Go networking helper. The earlier APK-derived Horizon packages target **Java Edition 26.3** and remain separate.

## Bedrock PC version 0.3.0

[Download Herspers Bedrock 0.3.0 for Windows x64](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41328863931/artifacts/13092278093). The package passed native startup, helper, resource-planner and visible setup-window checks. See [build results](docs/BEDROCK-WINDOWS-BUILD-RESULTS.md).

The Bedrock app targets **1.26.60 / protocol 2225** and handles its resource setup inside the app:

1. Extract the complete **Herspers-Bedrock** package, install the [Microsoft Visual C++ x64 runtime](https://aka.ms/vc14/vc_redist.x64.exe) if missing, and open **Herspers-Bedrock.exe**.
2. Review the Minecraft EULA, then let the native setup screen download and prepare its pinned Bedrock resources.
3. Use the client menu to sign in, join a compatible server, or create/import a Bedrock world.

**No Java, JDK or manual `server.jar` setup is needed for this target.** The in-app download is the supported version's resource data; the package already contains the native client. Cinnabar's original branding remains visible. Its fixed resource snapshot is `v1.26.60.30-preview`, recorded in [the source/package lock](bedrock-upstream.lock.json).

The [Build Bedrock Windows app workflow](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/workflows/bedrock-windows.yml) checks the package and first-run screen before uploading **Herspers-Bedrock-Windows-x64**. See [Bedrock installation](docs/INSTALL-BEDROCK-WINDOWS.md) and [licenses/provenance](docs/BEDROCK-LICENSES.md). Online login, server behavior and imported worlds need testing with the user's own account and files.

The Rust launcher is GPLv3; the separately distributed Cinnabar engine is **PolyForm Noncommercial 1.0.0**. This combination is not an all-Rust networking stack or a blanket GPL relicense of the engine. The engine's noncommercial terms remain in force.

## Earlier Java Edition build status

- APK inspected without executing it; its embedded build ID matches public source commit `7301f6fdd7f470b11317276e7a11b4dc615c137a`.
- Source fetching, static inspection, and portable packaging tests run on Linux.
- Recovered engine/resource-preparer library tests: 161 passed, 3 ignored.
- Both native macOS builds passed release compilation, architecture/library checks, ad hoc signing and ZIP packaging in [GitHub Actions run 41295959995](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41295959995).
- Interactive game launch, full resource preparation and gameplay are **not yet tested**. The Mac apps are not Apple-notarized; the Windows package is unsigned.
- Windows version **0.2.0** passed native compilation, packaging, launcher tests, 161 engine/preparer library tests (3 ignored) and packaged-EXE startup checks in [run 41304885077](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41304885077).

## Windows PC version 0.2.3

Version **0.2.3** adds Rust shader-loader compatibility for **Complementary Reimagined r5.5.1**, **Complementary Unbound r5.5.1**, and the supplied **Fullbright Ubiquitous FUB 7.0** resource pack. See [shader installation and exact validation limits](docs/SHADERS.md). BSL still needs its original archive for validation.

**Host-Tailscale.cmd** and **Join-Tailscale.cmd** remain included for private multiplayer between remote PCs. The host starter discovers and binds only to your Tailscale address, backs up existing configuration, and sets private authentication mode so Herspers can join without its unimplemented Microsoft sign-in. See [the hosting guide](docs/HOSTING-TAILSCALE.md). The 16 MiB main-stack fix remains included.

[Download Windows Java 0.2.3](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41467802883#artifacts), named **Herspers-Minecraft-Windows-x64**. The package includes **SHADERS.txt** and the host/friend instructions. The native build and private-server configuration smoke checks passed; see [build results](docs/JAVA-0.2.3-BUILD-RESULTS.md). Sign in to GitHub if asked, extract both ZIP layers, and keep the complete application folder together. It targets Windows 10/11 x64. Full gameplay and an actual two-PC Tailscale session remain unverified.

Owners of the earlier 0.2.0 package can use the [stack repair instructions](docs/INSTALL-WINDOWS.md#troubleshooting) without preparing resources again. The [earlier build evidence](docs/WINDOWS-BUILD-RESULTS.md) describes 0.2.0; it does not validate the revised binary.

1. Install JDK 25 and launch your own Minecraft Java Edition 26.3 once.
2. Double-click **Setup.cmd** and paste the path to the matching official 26.3 server JAR.
3. Wait for **Resources are ready**, then double-click **Play.cmd**.

If you already prepared resources on this PC, the new package reuses them; you can skip **Setup.cmd**.

To play with your friend over Tailscale:

1. **Both PCs:** extract the complete Windows Java 0.2.2 or newer package, prepare resources if needed, and connect Tailscale. Give your friend access to the host PC through your Tailscale network or device sharing.
2. **Your PC (host):** type `stop` in any old server window and wait for it to close. Open **Host-Tailscale.cmd**, read and accept the EULA if prompted, and keep this window open.
3. **Your PC:** send your friend the address printed in the host window, including its port. For example, `100.80.12.34:25565`; use your actual printed address.
4. **Both PCs:** open **Join-Tailscale.cmd**, enter that same host address, and choose different player names of 3–16 letters, numbers or underscores. The host joins this way too; use the printed address instead of `localhost`. Keep the same names on future visits.
5. **When finished:** leave the game, then type `stop` in the host's server window to save and shut down.

Read the [step-by-step Tailscale guide](docs/HOSTING-TAILSCALE.md), also included as **HOSTING-TAILSCALE.txt** in the download. The [Windows installation guide](docs/INSTALL-WINDOWS.md) covers setup and troubleshooting; [Java 0.2.3 build results](docs/JAVA-0.2.3-BUILD-RESULTS.md) record validation. No Rust, Python or developer tools are needed for the downloaded app. Full gameplay testing with prepared resources remains separate from build/startup checks.

## Java shader compatibility update 0.2.3

The 0.2.3 source adds Rust renderer compatibility for original **Complementary Reimagined r5.5.1** and **Complementary Unbound r5.5.1** shader ZIPs, and recognizes the supplied **Fullbright Ubiquitous FUB 7.0** resource pack. The verified Windows download is linked above; the verified Apple Silicon and Intel Mac downloads are below. See [Java 0.2.3 build results](docs/JAVA-0.2.3-BUILD-RESULTS.md).

The Complementary packs have drawn original synthetic terrain through real shadow, geometry and post passes on software Vulkan. These tests check pixel readback and HLSL/Metal shader generation; they do not establish complete gameplay or identical visuals on every GPU. **BSL is still awaiting its original ZIP for validation because its official download hosts are blocked in the cloud environment.**

Read [shader and Fullbright installation](docs/SHADERS.md). Original shader ZIPs belong in **Shader Packs**; the uploaded Fullbright ZIP belongs in **Resource Packs**. The author archives are separate from the application download, and the Bedrock build has not received these changes.

## Download Java 0.2.3 for Mac

- [Apple Silicon (arm64)](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41467803275#artifacts) — artifact **Herspers-Minecraft-arm64**.
- [Intel (x86_64)](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41467803275#artifacts) — artifact **Herspers-Minecraft-x86_64**.

Sign in to GitHub to download. Each artifact contains an architecture-specific ZIP; extract that ZIP to obtain `Herspers Minecraft.app`. These are development builds, and game assets are not included. Follow the [step-by-step Mac installation guide](docs/INSTALL-MACOS.md) before playing. See [Java 0.2.3 build evidence](docs/JAVA-0.2.3-BUILD-RESULTS.md).

## Install the downloaded app

See [Install Herspers Minecraft on a Mac](docs/INSTALL-MACOS.md) for downloading, moving the app into Applications, installing JDK 25, preparing resources and opening the app.

After installing JDK 25 and launching your own Minecraft Java Edition 26.3 once, run this in Terminal:

```bash
"/Applications/Herspers Minecraft.app/Contents/Resources/prepare.command"
```

Choose the matching official 26.3 server JAR when prompted. Wait for **Resources are ready**, then open the app. See the guide for a custom Minecraft installation folder or macOS security prompts.

## Build on a Mac

Requires macOS 11+, Apple's Command Line Tools (`xcode-select --install`), Python 3.9+, and Rust installed using [rustup](https://rustup.rs/). The build script installs the pinned Rust 1.95.0 toolchain and target libraries, fetches checksum-locked source, builds the game and preparation tools with audio/controllers/mods, checks binary architectures and library dependencies, then signs ad hoc and packages each app.

```sh
bash scripts/build_macos.sh both
# Or: arm64 / x86_64
```

Expected first-build outputs: `dist/arm64/Herspers Minecraft.app` and `dist/x86_64/Herspers Minecraft.app`, plus architecture-specific ZIPs. Repeated builds preserve existing packages and use fresh `build.*` subdirectories. These are separate builds, not a universal executable. They use the existing Horizon desktop engine and Metal renderer. The in-game interface keeps Horizon's branding.

The **Build macOS apps** GitHub Actions workflow performs the same builds automatically when build-related files are pushed to `main`, and can also be run manually. It uploads build artifacts; it does not publish a release or establish gameplay readiness. Build both versions and test on the corresponding Macs before distribution. Ad hoc signing is not Developer ID signing or Apple notarization.

## Prepare game resources and play

This section applies to the earlier **Java Edition** packages. **Bedrock 0.3.0 uses the in-app setup described above.**

The app does not ship Minecraft assets or reuse the generated game tables from the APK. Install and launch your own **Minecraft Java Edition 26.3** once, have its matching server JAR available, and install **JDK 25** for resource preparation.

For a downloaded app in Applications, follow the [installation guide](docs/INSTALL-MACOS.md). If you built from source, run the app's bundled preparation command from the repository directory:

```sh
"dist/arm64/Herspers Minecraft.app/Contents/Resources/prepare.command" "/absolute/path/server.jar"
```

Use `dist/x86_64` for Intel. The command accepts the Minecraft installation directory as a second argument if it differs from `~/Library/Application Support/minecraft`. It verifies the pinned game files through Horizon's preparer. Prepared resources, scratch files, and game saves live under `~/Library/Application Support/Herspers Minecraft`, outside the application and source tree.

Open the resulting app after preparation succeeds. This build uses the desktop client's own UI; it does not include the separate upstream auto-updating launcher or implement a new account manager. Online server access must be tested separately with the appropriate account/session support.

For a representative isolated world-rendering check on each Mac:

```sh
bash scripts/smoke_macos.sh "dist/arm64/Herspers Minecraft.app" \
  "$HOME/Library/Application Support/Herspers Minecraft/resources/26.3"
```

This requires 1,500 rendered world frames, generated/meshed chunks, a player and no reported error. It does not touch existing player saves.

## Inspect and test on Linux or macOS

```sh
python3 tools/inspect_apk.py /path/Horizon-Android-0.7.6-armeabi-v7a.apk
python3 tools/fetch_upstream.py
python3 -m unittest discover -s tests -v
# Include the real APK integration test when the file is available:
HORIZON_TEST_APK=/path/Horizon-Android-0.7.6-armeabi-v7a.apk python3 -m unittest discover -s tests -v
```

Dependencies and fetched source stay in ignored `.cache/`; upstream `Cargo.lock` is preserved and builds use `--locked`. A source-cache stamp records origin, not subsequent local edits. Keep an unmodified cache for reproducible builds. See [APK analysis](docs/APK-ANALYSIS.md), [source lock](upstream.lock.json), and [machine-readable audit](docs/apk-audit.json).

## Attribution

The independent project launchers/tools are licensed under [GPLv3](LICENSE), as selected in the GitHub repository. The Bedrock engine is an unchanged, checksum-pinned Cinnabar distribution with its original **PolyForm Noncommercial 1.0.0** license and notices. See [Bedrock licenses](docs/BEDROCK-LICENSES.md); commercial use needs appropriate permission from Cinnabar's licensors.

The older Java Edition packages use Horizon, which retains its MIT license, copyright Ludovic Marie and the Horizon contributors. Its license and third-party notices are retained under [licenses](licenses). Packaging copies applicable upstream license texts into each app. Minecraft game files have separate terms. This project is unofficial and is not endorsed by Mojang, Microsoft, Cinnabar or Horizon's maintainers.
