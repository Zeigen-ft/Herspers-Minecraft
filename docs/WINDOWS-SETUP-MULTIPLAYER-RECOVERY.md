# Windows setup and multiplayer recovery (Java Edition 26.3)

This is a **safe, repeatable recovery checklist** for Herspers Minecraft / Herps Launcher on Windows. It documents a user-reported setup failure and a subsequent successful friend connection; it is **not** a claim that the underlying cause has been fixed in code, or that three-player gameplay has been stress-tested.

## Before each new installation or update

1. Download the correct Windows x64 package from the repository's official release/build page; fully extract all nested ZIP files and keep the application folder intact.
2. Back up worlds and the server directory **while the game and server are stopped**. Do not delete `%APPDATA%\.minecraft`, `%LOCALAPPDATA%\Herspers Minecraft`, or an existing server world as a troubleshooting shortcut.
3. Install and launch the legally owned **Minecraft Java Edition 26.3** once using the official Minecraft launcher. Obtain the **matching official 26.3 server JAR** (do not extract it).
4. Install a **full JDK 25**, not just a JRE. In **Command Prompt (CMD)**, run each command separately and press Enter after every line:

   ```bat
   java -version
   javac -version
   where java
   where javac
   ```

   Both version commands must report 25, and the first `where` results should resolve to the intended JDK. If another Java is first, use the actual JDK installation directory in the following **same CMD window**:

   ```bat
   set "JAVA_HOME=C:\Program Files\Java\YOUR-ACTUAL-JDK-25-FOLDER"
   set "PATH=%JAVA_HOME%\bin;%PATH%"
   java -version
   javac -version
   ```

   The directory is an example, **not** a literal path to paste unchanged. `set` changes only the current CMD session; keep it open to run setup.

5. Open CMD in the extracted **Herspers-Minecraft** game folder (in a combined launcher package, look inside `game\Herspers-Minecraft`). Run **one command at a time**:

   ```bat
   call Setup.cmd
   ```

   At the prompt, paste the full path to the official **26.3 server JAR**, using File Explorer → Shift+right-click → **Copy as path**. Wait for **Resources are ready**. Do not proceed after a preparation error. Then run the game/launcher and validate the installation.

## Common Windows command-entry mistakes

- `invalid flag: -versioncd` means `javac -version` and `cd` were accidentally concatenated. They are **two separate commands**.
- `'Setup.cmdjavac' is not recognized` means `Setup.cmd` and `javac` were concatenated. Run `call Setup.cmd` **by itself**.
- `& was unexpected at this time` can mean PowerShell syntax was entered in CMD. Use the shell explicitly named in the instructions.
- A working `java -version` alone does **not** prove that `javac` is available or that `JAVA_HOME` points to JDK 25.

## Version manifest SHA-1 mismatch: safe recovery

Example failure observed during setup:

```text
...\.minecraft\versions/26.3/26.3.json is not a 26.3 version file Horizon knows
(sha1 ead839cbccf0ddf013c3f935f2840080b5cb0d26)
Herspers Minecraft: Resource preparation failed.
```

This means Horizon rejected the **version metadata**; it is **not evidence of a broken JDK**. First retry after installing and launching the exact official 26.3 version. If the preparer prints an **official Mojang metadata URL and an exact preparation-cache destination**, use *those values from your current error*, not an assumed path or an arbitrary JSON file.

For the **specific error above**, Horizon suggested this official URL:

```text
https://piston-meta.mojang.com/v1/packages/11f1aefe473eefba0af62e3286c33b692807b2eb/26.3.json
```

It suggested saving it as `manifest.json` under this preparation directory (the long hash is specific to that installation and may change):

```text
%LOCALAPPDATA%\Herspers Minecraft\preparation\f7fa494b766389caf06d98b4f77c7a5ea475bbe346d47d53224cbe5f24e61f70\.local\minecraft\26.3\
```

If **your current error prints exactly that destination**, you can use the following in **Windows PowerShell**, not CMD:

```powershell
$folder = Join-Path $env:LOCALAPPDATA 'Herspers Minecraft\preparation\f7fa494b766389caf06d98b4f77c7a5ea475bbe346d47d53224cbe5f24e61f70\.local\minecraft\26.3'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$url = 'https://piston-meta.mojang.com/v1/packages/11f1aefe473eefba0af62e3286c33b692807b2eb/26.3.json'
Invoke-WebRequest -Uri $url -OutFile (Join-Path $folder 'manifest.json')
Get-FileHash -Algorithm SHA1 -LiteralPath (Join-Path $folder 'manifest.json')
```

Re-run `Setup.cmd` in CMD afterward. This workaround is **documented, not confirmed as a permanent fix**. Do **not** replace the official `%APPDATA%\.minecraft\versions\26.3\26.3.json` with an unverified file, bypass Horizon's SHA checks, or erase saves. If the same error recurs, retain the full console output and report the issue so the preparer's manifest selection and validation can be fixed in code.

## Multiplayer: prevent avoidable three-player stalls

The host can play and host on the same PC, but the game and server share CPU, RAM, disk, and network resources. A 60 FPS overlay with ~16.7 ms frame time shows **client rendering**, not server TPS or tick health.

1. Stop old servers gracefully with `stop`. Back up the server folder, then start **Host-Tailscale.cmd** (for supported Windows Java packages) and keep its console open. Both host and friends connect through Tailscale using the **printed address including port**, with distinct stable player names. Never publish the private Tailscale address in a public bug report.
2. Test one player, then two, then three **standing together without vehicles**. Next test with vehicles and exploration separately. Note exactly when delays begin.
3. On the host, use Task Manager → Performance to record **CPU, RAM, disk and network** during two-player and three-player sessions. Check whether the server tick rate drops (where the server supports TPS/MSPT commands). Do not confuse a client's FPS with TPS.
4. If using a compatible standard Java server, consider `view-distance=6` and `simulation-distance=4` in `server.properties` **after backing it up and stopping the server**. Confirm these properties are supported by the actual server before changing them. Reduce client graphics load if the host also plays.
5. If the console floods with `vehicle 7 moved wrongly` / `vehicle 7 moved too quickly`, reproduce with everyone **off vehicles**. These warnings suggest movement correction/desynchronization but do **not** prove that vehicles caused the slowdown. Do not disable movement validation to silence warnings.
6. For recurring lag, preserve server `logs\latest.log`, the host console output, `%LOCALAPPDATA%\Herspers Minecraft\logs\launcher.log`, server software/version, player count, whether vehicles were used, and host CPU/RAM readings. Remove usernames, private addresses, tokens and session data before sharing.

## Completion checklist

- [ ] Full JDK 25 checked with **both** `java` and `javac`.
- [ ] Exact official Minecraft Java 26.3 client and server JAR used.
- [ ] Setup ended with **Resources are ready** and the launcher validates resources.
- [ ] Existing worlds backed up and retained.
- [ ] Host and friend successfully join with distinct names and the printed Tailscale address.
- [ ] Three-player standing-still and vehicle tests completed without recurring server stalls.
- [ ] Logs and system measurements saved if a failure recurs.

**Important:** A successful friend connection is not proof that every three-player or vehicle issue is fixed. Permanent prevention requires reproducible evidence, a code change, and real multi-client regression testing.
