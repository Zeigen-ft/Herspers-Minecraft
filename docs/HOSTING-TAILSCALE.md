# Private multiplayer over Tailscale (Windows Java 0.2.2 and newer)

You and your friend can play from different locations, including 100 km apart. Your PC runs the server, and Tailscale connects your friend's PC to it. Follow these steps on both PCs; no router port forwarding is needed.

## On both PCs first

1. Download **Windows Java 0.2.2 or newer** from the [Windows builds page](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/workflows/windows.yml). Open the latest successful Java build. Sign in to GitHub if needed, scroll to **Artifacts**, and select **Herspers-Minecraft-Windows-x64**.
2. Extract the downloaded ZIP. Inside it, extract the application ZIP too. Open the resulting **Herspers-Minecraft** folder, where **Host-Tailscale.cmd** and **Join-Tailscale.cmd** are located. Keep the whole folder together.
3. Check that Herspers has its Java Edition 26.3 resources ready. If it already says **Resources are ready**, skip Setup. If this is a new installation without prepared resources, read **INSTALL-WINDOWS.txt** in the application folder or the [Windows installation guide on GitHub](https://github.com/Zeigen-ft/Herspers-Minecraft/blob/main/docs/INSTALL-WINDOWS.md), and run **Setup.cmd** once.
4. Install and connect [Tailscale](https://tailscale.com/download) on both PCs. Give your friend access to your host PC through your Tailscale network or device sharing. Both PCs must stay connected to Tailscale while playing.

## On your PC (host)

1. If an older Minecraft server is still running, type **`stop`** in its server window and wait for it to close.
2. Open **Host-Tailscale.cmd** in the extracted application folder. If prompted, read the [Minecraft EULA](https://aka.ms/MinecraftEULA) and type **I AGREE** only if you agree.
3. Wait for the server to start. Copy the address printed in the host window and send it to your friend. It will look like **100.80.12.34:25565**; use your actual printed address, including **`:25565`**, rather than this example.
4. **Keep the host window open.** Open **Join-Tailscale.cmd** in a second window on your PC.
5. Paste the same host address when asked. Choose your player name using **3–16 letters, numbers or underscores**. Use a different name from your friend and keep using that name on later visits.

## On your friend's PC

1. Open **Join-Tailscale.cmd** in their extracted application folder.
2. Paste the exact address you sent, including the port after the colon.
3. Enter a different player name using **3–16 letters, numbers or underscores**. Keep using that name on later visits.

**Both players use the host's printed Tailscale address.** Do not enter `localhost` on either PC: this server listens on its Tailscale address.

## When finished

1. Both players leave the server in the game.
2. On the host PC, type **`stop`** in the server window and wait for it to save and exit.
3. Next time, connect Tailscale, open **Host-Tailscale.cmd**, then open **Join-Tailscale.cmd** on both PCs. Use the newly printed host address and the same player names.

## Server folder and backups

The host reuses `Documents\Herspers-Server` if it contains `server.properties`, matching the earlier manual setup. Otherwise the default is `%LOCALAPPDATA%\Herspers Minecraft\servers\tailscale`. The host window prints the server folder; it contains the world, properties and logs.

The starter saves configuration backups with unique names and preserves existing worlds, player files and accepted EULAs. It reports an occupied port and never kills another server process. Stop the server before making a separate backup of its folder.

## Troubleshooting

- **Host-Tailscale.cmd or Join-Tailscale.cmd is missing:** download the latest successful **0.2.2 or newer** Windows Java build again, extract both ZIPs, and open the complete application folder. An older application folder may not contain these starters.
- **Still says online mode:** that message means the server requires Microsoft authentication, which this launcher does not provide. Stop the old server, launch **Host-Tailscale.cmd**, and have both players join its newly printed address. In the printed server folder, `server.properties` must contain the current Tailscale `server-ip` and `online-mode=false`. Restarting is necessary for changed server settings to take effect.
- **Cannot listen / port occupied:** connect Tailscale, stop the old server, then retry. If you intentionally run another server, choose a different port with the advanced command below.
- **Connection times out:** check Tailscale's device-sharing/network access first. If a Windows Firewall rule is needed, allow this application's `bin\horizon-client.exe` for TCP on the selected port, scoped to the host's Tailscale local address and remote range `100.64.0.0/10`. Do not disable the firewall.
- **Missing resources:** read **INSTALL-WINDOWS.txt** or the [Windows installation guide on GitHub](https://github.com/Zeigen-ft/Herspers-Minecraft/blob/main/docs/INSTALL-WINDOWS.md) and run **Setup.cmd** once on the affected PC. Existing prepared resources are reused; creating a server does not require another resource export.
- **Server error:** retain its console output and `logs\latest.log` in the printed server folder. Client errors are in `%LOCALAPPDATA%\Herspers Minecraft\logs\launcher.log`.

## Advanced options

The starter binds the server only to the host's Tailscale address and uses `online-mode=false`. This is a private server without Microsoft account verification. Invite the intended friends through Tailscale; its sharing permissions and Windows Firewall control who can reach the server. Player identities depend on their names, so keep those names stable. These identities differ from authenticated account identities.

You can also use **Multiplayer → Direct Connection** in an existing Java Edition 26.3-compatible client and enter the host's printed address.

For a different server folder or port, run these commands from the application folder:

```powershell
.\Herspers-Minecraft.exe --host-tailscale --server-dir "D:\My Private Server" --port 25566
.\Herspers-Minecraft.exe --join-tailscale 100.80.12.34:25566 --name YourName
```

The optional `--accept-eula` flag is for automation only when the operator agrees to the [Minecraft EULA](https://aka.ms/MinecraftEULA). The normal starter asks before accepting a previously unaccepted EULA.

The rebuild checks the real server's configuration parser without assets and tests private-address validation, backups and launch arguments. An actual two-PC Tailscale session still needs validation on the players' machines.

## Private multiplayer troubleshooting

1. In **Herps Launcher → Multiplayer**, enter **In-Game Player Name** and choose **Save player name** before starting the game. Use 3–16 letters A–Z, digits or underscores. If you see a generated name, close the game, save the name, and relaunch. With the standalone Windows game, open **Join-Tailscale.cmd** and enter the name at the prompt.
2. Give each player a unique name. An offline host uses the name to identify saved player data. Switching names can show an empty inventory. Close the other session if the host reports a duplicate login. Rejoin with the original spelling and capitalization to access the original inventory.
3. If the game returns to the server list, record the time and any disconnect message. In File Explorer, open `%LOCALAPPDATA%\Herspers Minecraft\herps-launcher\logs` for GUI-launched sessions. On the host, open `logs\latest.log` inside the active server folder. Share a short excerpt from each after removing names, private addresses and tokens.
4. On a **copy** of the world, join with one, two and then three players. Stand still first, then explore; repeat with a vehicle. Record which players freeze. FPS measures one client's frames. TPS measures how often the host advances the world (normally 20 times per second). A smooth server list after a disconnect tells you neither the earlier frame time nor the host's TPS.
5. For a short diagnostic run in Windows Command Prompt, enter `set HORIZON_SPIKES=50` and start the client or host **from that same window**. Repeat the problem once and close the window afterward. Look for slow frame or server-tick spans, chunk backlog and the final disconnect reason. A movement warning alone does not identify what slowed down.
6. Before rollback, type `stop` in the host console and wait for it to exit. Close the game and copy the **whole server folder** and the affected client profile to a separate backup location. Run the previous matching client and host builds on copies. Keep the original world, player data and backups.

[Windows setup and multiplayer recovery checklist](https://github.com/Zeigen-ft/Herps-Launcher/blob/6e3d580/docs/WINDOWS-SETUP-MULTIPLAYER-RECOVERY.md)
