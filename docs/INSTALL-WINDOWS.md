# Install Herspers Minecraft 0.2.3 on a Windows PC

This version targets **Windows 10 or 11, 64-bit Intel/AMD PCs**. It is not an Android APK. Windows on ARM and 32-bit Windows are not supported by this package.

The game needs a graphics driver supporting DirectX 12, Vulkan or the engine's OpenGL fallback. Build and startup check results are listed in the repository README; those checks do not establish working gameplay on every PC.

## 1. Download and extract

Open [Actions → Build Windows PC app](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/workflows/windows.yml) and select the latest successful run for **0.2.3**. Scroll to **Artifacts** and download **Herspers-Minecraft-Windows-x64**. Sign in to GitHub if needed. Version 0.2.3 adds Rust shader-loader compatibility fixes and keeps the private Tailscale starters and 16 MiB stack fix. A successful build does not establish full gameplay readiness.

Extract the downloaded artifact ZIP, then extract the application ZIP inside it. Keep the entire **Herspers-Minecraft** folder together, including `bin`, `preparation`, `Setup.cmd`, `Play.cmd`, `Host-Tailscale.cmd` and `Join-Tailscale.cmd`. For example, keep it in your Documents or Games folder. Do not run individual files from inside the ZIP.

**Updating an existing installation?** Previously prepared resources and saves stay outside this application folder. If setup already reported **Resources are ready** on this PC, skip steps 2–3 and go to step 4 for single-player or step 5 for Tailscale multiplayer.

No Rust, Python, Visual Studio or administrator access is required to use the downloaded app. The package is unsigned; Windows may show a publisher warning. Only run the package you chose to download from this repository.

## 2. Prepare your Minecraft files

Install the following:

- A full **JDK 25 for Windows x64**, such as [Eclipse Temurin JDK 25](https://adoptium.net/temurin/releases/?version=25). Choose **Windows**, **x64**, **JDK** and the installer. A JRE alone is insufficient.
- Your own **Minecraft Java Edition 26.3**, installed and launched once with the official launcher.
- Its matching official **Java Edition 26.3 server JAR**, downloaded from that version's official download information.

The server JAR is an input to preparation. You do not need to run or host a Minecraft server. The package does not contain Minecraft assets. This engine targets Java Edition; installing Bedrock does not supply its required files.

## 3. Run first-time setup

Double-click **Setup.cmd** in the extracted folder.

When asked for the server JAR, paste its full path and press Enter. Select the original **`.jar` file**, keeping it unextracted; a folder such as `META-INF\versions\26.3` will not work. Windows **Copy as path** is useful here; surrounding quotes are accepted. For example:

```text
"C:\Users\YourName\Downloads\server.jar"
```

Keep the window open until it says:

```text
Resources are ready. You can now open Herspers-Minecraft.exe.
```

If setup fails, read the error before closing the window. The preparer verifies the pinned game files and JDK requirements.

### Command-line setup or a custom installation folder

Open Terminal or PowerShell in the extracted application folder. This starts the same setup prompt:

```powershell
.\Herspers-Minecraft.exe --setup
```

The default Minecraft installation folder is `%APPDATA%\.minecraft`. To use a custom folder, supply the server JAR first and the Minecraft installation folder second:

```powershell
.\Herspers-Minecraft.exe --setup "C:\Downloads\server.jar" "D:\Minecraft"
```

Use the installation folder containing the version files and assets, rather than a world-save folder.

## 4. Play

After setup succeeds, double-click **Play.cmd** or **Herspers-Minecraft.exe**. Keep the `bin` and `preparation` folders beside the launcher.

The launcher checks resources before starting the game. If resources are missing, run **Setup.cmd** first. The bundled launcher does not implement a new Microsoft account manager; online server/account compatibility requires separate testing.

Game data stays under:

```text
%LOCALAPPDATA%\Herspers Minecraft
```

- `game`: saves and game settings.
- `resources\26.3`: prepared resources.
- `preparation`: preparation inputs and scratch files.
- `logs\resources-check.log`: startup resource-check results.
- `logs\launcher.log`: game startup output.

## 5. Play with a friend using Tailscale

1. **Both PCs:** complete the download and resource setup above. Install and connect [Tailscale](https://tailscale.com/download). Give your friend access to your host PC through your Tailscale network or device sharing, and keep Tailscale connected on both PCs.
2. **Your PC (host):** if an older server is running, type `stop` in its server window and wait for it to close. Open **Host-Tailscale.cmd** in the extracted application folder. If prompted, read the Minecraft EULA and type **I AGREE** only if you agree.
3. **Your PC:** wait for the server to start and copy the address printed in the host window. Send it to your friend, including the port after the colon. It will look like `100.80.12.34:25565`; use your actual printed address. **Keep the host window open.**
4. **Your PC:** open **Join-Tailscale.cmd** in a second window, paste the printed host address, and enter a player name of **3–16 letters, numbers or underscores**.
5. **Your friend's PC:** open **Join-Tailscale.cmd**, paste the same address, and enter a different player name. Keep using the same names on future visits. Both players use the host's Tailscale address; `localhost` will not work because this server listens on its Tailscale address.
6. **When finished:** both players leave the game, then the host types `stop` in the server window and waits for it to save and exit. Next time, connect Tailscale, open **Host-Tailscale.cmd**, then use **Join-Tailscale.cmd** on both PCs again.

No router port forwarding is needed. This starter creates a private server without Microsoft account verification and binds it only to the host's Tailscale address. Tailscale sharing controls which friends can reach it.

Read **HOSTING-TAILSCALE.txt** beside the launchers for server folders, backups and connection troubleshooting. The same [Tailscale hosting guide is available on GitHub](https://github.com/Zeigen-ft/Herspers-Minecraft/blob/main/docs/HOSTING-TAILSCALE.md).

## 6. Install a Java shader pack

Read **SHADERS.txt** beside the launchers for the exact tested pack versions and download links. Open **Options → Horizon Settings → Shader Packs → Open Pack Folder** in the game, copy the original shader ZIP there, then select it in the Shader Packs menu. Shader ZIPs go in `shaderpacks`, rather than the `mods` or `resourcepacks` folders. Shader packs are optional and are not bundled in the application.

The folder is `%LOCALAPPDATA%\Herspers Minecraft\game\shaderpacks`. The separate Bedrock client uses a different renderer; these instructions apply to Herspers Java Edition only. Keep shaders off if diagnosing an unrelated startup failure.

## Troubleshooting

- **JDK missing:** install the full JDK 25, then close and reopen the setup window. The preparer searches installed JDK folders, `JAVA_HOME` and PATH.
- **Wrong JAR/version:** use the matching official Java Edition 26.3 files. A different version is rejected.
- **Missing bundled file:** extract the complete package again; do not move only the launcher EXE.
- **Host-Tailscale.cmd or Join-Tailscale.cmd is missing:** download the latest successful Windows Java **0.2.2 or newer** package and extract both ZIP layers. Older packages do not include these starters.
- **Server still says online mode:** stop the old server, start **Host-Tailscale.cmd**, and use its newly printed address in **Join-Tailscale.cmd** on both PCs. See **HOSTING-TAILSCALE.txt** for further connection checks.
- **No graphics device or driver failure:** update your GPU driver and retain the startup log when reporting the problem.
- **`thread 'main' has overflowed its stack` at the menu:** early 0.2.0 packages used the Windows default main-thread stack. Current source builds reserve 16 MiB and packaging checks that value. To repair an existing unsigned package, close the game and place [repair_windows_stack.ps1](https://github.com/Zeigen-ft/Herspers-Minecraft/blob/main/scripts/repair_windows_stack.ps1) in the extracted application folder. Open PowerShell there and run:

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File .\repair_windows_stack.ps1 -PackagePath .
  ```

  The execution-policy override applies only to that invocation. The repair verifies the original game against `build-metadata.json`, then changes only its PE stack-reserve field. It keeps `bin\horizon-client.exe.before-stack-fix.bak`, preserves resources and saves, and refuses signed executables or an existing backup. The repaired executable will differ from the original metadata checksum; the metadata is preserved. Open `Play.cmd` to test. If the game already reserves 16 MiB, the script makes no change; send the new log for further diagnosis. `RUST_MIN_STACK` does not change the main thread's stack.

Include the error text and relevant logs in a bug report, without account tokens or private session files. Resource preparation and an interactive gameplay test on your PC remain necessary even after native build/startup checks pass.

## Build from source

Developers need Python 3.9+, rustup, PowerShell 7+, Visual Studio C++ Build Tools and the Windows SDK. From the repository folder, run:

```powershell
pwsh -File scripts/build_windows.ps1
```

The script uses Rust 1.95.0, the locked upstream source and its optimized `fast` profile (optimization level 3, with link-time optimization disabled). It produces a portable x64 ZIP under `dist/windows-x86_64`. For a full release-profile build, add `-Profile release`. Repeated builds preserve earlier packages in separate output folders. Full resource preparation and gameplay are separate from compilation.

## Join a private server

1. Start Tailscale and connect to the host's network.
2. Open **Join-Tailscale.cmd** in the installed game folder. Enter the host address, then a unique player name such as `CJ_Corto`. Use the same name on every visit to retain your offline player identity.
3. If you use Herps Launcher, open **Multiplayer → In-Game Player Name → Save player name**, enter the host address and select **JOIN**. After saving, you can also join from the game's multiplayer menu.
4. If disconnected, record the exact message and time before reconnecting. See [logs, three-player testing and safe rollback](HOSTING-TAILSCALE.md#private-multiplayer-troubleshooting).
