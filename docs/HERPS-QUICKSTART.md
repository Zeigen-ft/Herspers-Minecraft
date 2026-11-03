# Use or integrate Herps Launcher

Herps Launcher manages **Herspers Minecraft Java Edition 26.3**. Choose a route:

- **Install the complete app:** follow steps 1–3 below.
- **Connect an existing Herspers game:** follow [Connect an existing installation](#connect-an-existing-installation).
- **Work on the source or integrate the feature branch:** follow [Source and repository integration](#source-and-repository-integration).

Bedrock is a separate application. These instructions use the Java Edition packages.

## 1. Download your platform package

Sign in to GitHub if prompted, download the artifact, and **extract its outer ZIP**:

| Your computer | Download | File to open after extraction |
| --- | --- | --- |
| Windows 10/11, Intel or AMD x64 | [Windows package](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41571739445/artifacts/13202422947) | `Herps-Launcher-0.1.0-Windows-x64-Setup.exe` |
| Mac with an Apple M-series chip | [Apple Silicon package](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41571739445/artifacts/13202148293) | The `.dmg` file |
| Mac with an Intel processor | [Intel package](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41571739445/artifacts/13202408890) | The `.dmg` file |

On a Mac, **Apple menu → About This Mac** shows whether you have an Apple chip or Intel processor. Herps Launcher requires macOS 12 or later.

### Windows installation

1. Install the [Microsoft Visual C++ x64 runtime](https://aka.ms/vc14/vc_redist.x64.exe) if it is missing.
2. Run the extracted `-Setup.exe` and choose an installation folder. Enable the optional desktop shortcut if wanted.
3. Open **Herps Launcher** from the Start Menu or desktop shortcut.
4. Continue to [Prepare resources and play](#2-prepare-resources-and-play).

For a portable installation, extract the inner application ZIP instead of running the installer. Open `Herps Launcher/Herps Launcher.exe` and keep its `_internal`, `game`, and `engine-source` folders with it.

The Windows build is unsigned. If Windows displays a publisher warning, review the download source. If you trust this build and Windows offers the option, choose **More info → Run anyway**.

### Mac installation

1. Open the extracted DMG.
2. Copy **both** `Herps Launcher.app` and `Herspers Minecraft.app` into **Applications**.
3. Open **Herps Launcher** from Applications.
4. If macOS blocks this development build, review **System Settings → Privacy & Security** after attempting to open it; on macOS 12, use **System Preferences → Security & Privacy**. Use **Open Anyway** if offered and you trust this build. These apps have ad hoc signatures and are not notarized.
5. Continue to resource preparation below.

If you intend to build native mods, also copy the complete `engine-source` folder out of the DMG to a permanent location, such as Documents. The launcher will need that folder after the DMG is ejected.

## 2. Prepare resources and play

If your Herspers Java 26.3 resources are already prepared on this computer, go directly to step 6.

1. Install a full **JDK 25**, including `java` and `javac`.
2. Install and launch your own **Minecraft Java Edition 26.3** once through the official launcher.
3. Have that exact version's matching official **server JAR** available. Keep the `.jar` file unextracted; it is a preparation input, and you do not need to start a server.
4. Run the existing preparation command for your platform:
   - **Windows:** in Herps Launcher, open **Settings** and find the displayed **Herspers folder / .app** path. Open that folder in File Explorer and double-click **Setup.cmd**. In the portable package, it is under `Herps Launcher/game/Herspers-Minecraft`.
   - **Mac:** open Terminal and run:

     ```bash
     "/Applications/Herspers Minecraft.app/Contents/Resources/prepare.command"
     ```

5. Select or enter the matching server JAR when asked. Keep the preparation window open until it says **Resources are ready**. If it fails, resolve the displayed error before continuing.
6. Open **Herps Launcher → Settings → Validate installation**. If the game was not found, use **Find installation…** as described below.
7. Open **Home**, select the **default** profile, and click **PLAY →**.
8. After leaving the game, wait for its exit code to appear in the launcher. You can then press PLAY again.

Package validation checks the installed binaries; PLAY separately checks the prepared resources. Minecraft assets are not included. Custom Minecraft-folder instructions are in the [Windows guide](INSTALL-WINDOWS.md#command-line-setup-or-a-custom-installation-folder) and [Mac guide](INSTALL-MACOS.md#if-your-minecraft-installation-is-in-a-different-folder).

## Connect an existing installation

1. Close the game and its old launcher.
2. Open **Herps Launcher → Settings → Find installation…**.
3. Select the complete compatible package:
   - **Windows:** the `Herspers-Minecraft` folder containing `upstream.lock.json`, `build-metadata.json`, `bin`, and `Setup.cmd`.
   - **Mac:** the whole `Herspers Minecraft.app` bundle.
4. Click **Validate installation** and check the version and architecture shown.
5. Open **Home**, select **default**, and press **PLAY →**. Previously prepared resources and existing Herspers saves are reused.

**Find installation…** saves the selected path immediately. If you type a path manually, click **Save settings**. Select the Herspers package rather than `.minecraft`, a bare executable, `bin`, or `Contents/MacOS`: `.minecraft` is an input to resource preparation, while the selected package contains the runnable Herspers client.

This integration launches the existing client directly. It does not inject files into the official Minecraft launcher or require the original Horizon Launcher.

### Existing saves and profiles

The **default** profile uses existing Herspers game data:

| Platform | Default game data |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Herspers Minecraft\game` |
| Mac | `~/Library/Application Support/Herspers Minecraft/game` |

Use **Settings → Open game data and saves** to open the selected profile's folder. **Home → + New profile** creates a separate game folder; it does not automatically copy existing worlds. Close the game and wait for any build to finish before changing profiles, mods, shaders, or settings.

## 3. Install mods or shaders

### Runtime/content mods: `.hmod`

1. Choose your profile on **Home**.
2. Open **Mods → Import mod…** and select the `.hmod` file.
3. Select the imported mod's row and review its API, side, and capabilities. Imports start disabled.
4. Click **Enable / disable** to turn it on.
5. Return to **Home → PLAY →**.

Forge/Fabric `.jar` mods are incompatible with this Horizon mod format. **Remove to backup** removes a package from the profile while retaining a backup and its mod data.

### Native-source mods: `.hnmod`

1. Install Rust **1.95.0** using rustup and the native build tools: Visual Studio C++ Build Tools plus Windows SDK on Windows, or Xcode Command Line Tools on Mac.
2. In **Settings → Prepared native source**, paste the full path to the matching, complete `engine-source` folder **without surrounding quotes**. Review the other visible settings and click **Save settings**.
3. Import the `.hnmod` through **Mods → Import mod…**.
4. Select the row, review its source/compatibility, and enable it only if you trust it.
5. Click **Rebuild native mods…**, review the trust prompt, and wait for **Native build completed**. Compilation can take several minutes; its output appears in the Mods log panel.
6. Return to **Home → PLAY →**. The selected profile uses the matching rebuilt binary.

Native mods execute build scripts and game code with your permissions. Each supported platform/architecture needs its own build. Use **Roll back · disable all native mods** to select the original game binary again. If the enabled native-mod set changes, rebuild when requested. See [the compatibility contract](HERPS-LAUNCHER.md#mods-and-native-builds) for exact revision requirements. Windows native compilation and rollback were exercised in CI; Mac native-mod compilation remains unverified.

### Shader packs

1. Open **Shaders → Import pack…** and choose a compatible shader `.zip` or `.hshader`.
2. Select its row and click **Select pack**.
3. Return to **Home → PLAY →**. The game loads and validates the selected pack on the actual GPU.
4. If it fails, close the game, click **Shaders → Restore default shaders**, and launch again.

Shader import/selection does not establish successful rendering. Mac uses Metal; Windows backend preferences are under Settings. Fullbright/resource-pack ZIPs belong in the game's resource-pack system; see [shader and resource-pack instructions](SHADERS.md).

## Play with a friend over Tailscale

1. Prepare resources on both computers, connect Tailscale, and grant the friend access to the host computer through your tailnet or device sharing.
2. On both computers, open **Multiplayer → Refresh Tailscale status** and check that it reports connected.
3. On the host, stop any old server with `stop`, then click **Open existing hosting console**. Read and accept the EULA if you agree, and keep that console open.
4. Copy the host address printed there, including the port, for example `100.80.12.34:25565`. Use the host's actual printed address.
5. On **both** computers, enter that address in **Host address**, enter different **Private player name** values of 3–16 letters, digits, or underscores, and click **JOIN →**. The host joins this way too.
6. Use **Save favorite** to keep the address. When finished, leave the game and type **stop** in the server console to save and shut down.

The host's Tailscale address is required; the private server binds to that address. The existing Herspers private-server behavior is preserved. An end-to-end two-computer session has not yet been verified. See [hosting details and troubleshooting](HOSTING-TAILSCALE.md).

## Source and repository integration

### Run the launcher from source

Use Python **3.12** and a compatible prebuilt Herspers game package. The source checkout does not include compiled game binaries. In an existing checkout, preserve your local changes and use the feature branch. A new checkout can be created with:

```sh
git clone --branch feature/herps-launcher-cross-platform https://github.com/Zeigen-ft/Herspers-Minecraft.git
cd Herspers-Minecraft
```

In an isolated cloud task, use its existing checkout; no additional worktree is needed.

**Windows, PowerShell:**

```powershell
py -3.12 -m venv .local\herps-venv
.\.local\herps-venv\Scripts\python.exe -m pip install -r herps_launcher\requirements.txt
.\.local\herps-venv\Scripts\python.exe -m herps_launcher
```

**Mac:**

```bash
python3.12 -m venv .local/herps-venv
.local/herps-venv/bin/python -m pip install -r herps_launcher/requirements.txt
.local/herps-venv/bin/python -m herps_launcher
```

Connect your prebuilt game through **Settings → Find installation…**. Normal use of the downloaded app does not require Python, Rust or a source checkout.

Source-mode Mac hosting additionally needs its helper compiled at the path the development launcher uses:

```bash
mkdir -p .cache
rustc +1.95.0 --edition=2021 packaging/herps_host.rs -o .cache/herps-host
```

### Build distributable packages

The existing native build scripts and `tools/package_herps.py` prepare the game, launcher and packaging. The [developer guide](HERPS-LAUNCHER.md#develop-and-package) explains prerequisites and package inputs. Run local builds on the matching Windows/Mac platform; use the printed output directory when a repeated build creates a `build-*` folder.

To run the repository's verified CI workflow with an authenticated GitHub CLI and repository access:

```sh
gh workflow run herps-launcher.yml --repo Zeigen-ft/Herspers-Minecraft --ref feature/herps-launcher-cross-platform -f platform=all
```

Use `platform=windows`, `platform=macos-arm64`, or `platform=macos-x64` to build one target. Inspect the workflow's conclusion, then download the corresponding artifact.

### Bring the feature into `main`

The implementation and this guide are on **`feature/herps-launcher-cross-platform`**. To integrate them into the repository's default branch, open a pull request with **base `main`** and **compare `feature/herps-launcher-cross-platform`**, review the changes and native CI evidence, and merge when you choose. No automatic merge has been performed.

Keep `herps_launcher/`, its pinned requirements, `tools/package_herps.py`, `tools/ci_run.py`, `tools/smoke_herps_native.py`, the `packaging/herps*` files and shared `packaging/private_server.rs`, launcher tests, the Herps workflow, and the existing source locks, patches and engine fetch/build/package tools together. The launcher relies on the repository's source lock and engine package metadata; copying only the GUI file is insufficient.

## If a step fails

| Symptom | Next step |
| --- | --- |
| No installation found | Use **Find installation…** and choose the complete compatible Herspers package. |
| Resource validation failed | Run the selected game's preparation command with JDK 25 and the exact matching game files; inspect `resources-check.log` in the launcher data folder. |
| Native mods need rebuilding | Set the matching prepared source folder, check Rust/build-tool availability, and run **Rebuild native mods…**. |
| Shader failure | Use **Restore default shaders** before retrying. |
| Game exits with an error | Use **Home → Open launcher and game logs** and inspect the newest run log. |

For validation results and remaining limits—including gameplay, shader rendering, live multiplayer and signing—see [the full launcher guide](HERPS-LAUNCHER.md#verification-boundaries).
