//! Shared console host entrypoint. Reuses the existing private server policy unchanged.
mod private_server;
use std::{env, fs, io::{self, Write}, path::PathBuf, process::{self, Command}};

fn run() -> Result<i32, String> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() != 3 {
        return Err("Usage: herps-host GAME-BINARY RESOURCES SUPPORT-FOLDER".into());
    }
    let binary = PathBuf::from(&args[0]);
    let resources = PathBuf::from(&args[1]);
    let support = PathBuf::from(&args[2]);
    if !binary.is_file() || !resources.is_dir() {
        return Err("Prepare your Herspers Java 26.3 resources before hosting.".into());
    }
    let bin_dir = binary.parent().ok_or("Game binary has no parent folder")?;
    let (preparer, inputs) = if cfg!(target_os = "macos") {
        (bin_dir.join("horizon-prepare"), bin_dir.parent().ok_or("Missing app Contents")?.join("Resources/preparation"))
    } else {
        (bin_dir.join("horizon-prepare.exe"), bin_dir.parent().ok_or("Missing package folder")?.join("preparation"))
    };
    let checked = Command::new(preparer).args(["--check", "--root"]).arg(inputs)
        .arg("--output").arg(&resources).status().map_err(|e| e.to_string())?;
    if !checked.success() { return Err("Game resource validation failed; run the existing preparation command first.".into()); }
    let ip = private_server::tailscale_ipv4()?;
    let port = 25565;
    let listener = std::net::TcpListener::bind((ip, port)).map_err(|e| format!("Cannot listen on {ip}:{port}: {e}. Stop the previous host first."))?;
    drop(listener);
    let directory = private_server::server_directory(&support);
    let report = private_server::configure(&directory, ip, port)?;
    println!("Server configuration: {}", report.config_path.display());
    if let Some(backup) = report.backup { println!("Backup: {}", backup.display()); }
    if !report.eula_agreed {
        println!("Read https://aka.ms/MinecraftEULA");
        print!("If you agree, type I AGREE: ");
        io::stdout().flush().map_err(|e| e.to_string())?;
        let mut response = String::new();
        io::stdin().read_line(&mut response).map_err(|e| e.to_string())?;
        if !response.trim().eq_ignore_ascii_case("I AGREE") { return Err("EULA not accepted; server not started.".into()); }
        private_server::agree_eula(&directory)?;
    }
    fs::create_dir_all(&directory).map_err(|e| e.to_string())?;
    println!("HOST AND FRIEND JOIN: {ip}:{port}");
    println!("Existing Herspers private-server mode: bound only to Tailscale, private player names, no Microsoft account authentication.");
    println!("Keep this console open. Type stop to save and shut down.");
    let status = Command::new(binary).arg("--resources").arg(resources)
        .arg("--game-dir").arg(&directory).arg("--home").arg(&directory)
        .args(["--dedicated", "--nogui"]).current_dir(&directory)
        .env("HORIZON_HOME", &directory).env("HORIZON_NO_AUDIO", "1")
        .env("HORIZON_LAUNCHER_NO_SELF_UPDATE", "1").status().map_err(|e| e.to_string())?;
    Ok(status.code().unwrap_or(1))
}

fn main() {
    match run() {
        Ok(code) => process::exit(code),
        Err(error) => { eprintln!("Herps hosting: {error}"); process::exit(1); }
    }
}
