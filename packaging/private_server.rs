//! Private server configuration for an existing Tailscale installation.
//! Account verification is disabled only in a server bound to a tailnet IPv4.

use std::env;
use std::ffi::OsString;
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{Read, Write};
use std::net::Ipv4Addr;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

const CONFIG_LIMIT: usize = 1024 * 1024;
const EULA_DEFAULT: &[u8] =
    b"# Read https://aka.ms/MinecraftEULA before agreeing.\r\neula=false\r\n";
static SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug)]
pub struct Report {
    pub config_path: PathBuf,
    pub backup: Option<PathBuf>,
    pub eula_agreed: bool,
}

fn tailnet(ip: Ipv4Addr) -> bool {
    let [a, b, _, _] = ip.octets();
    a == 100 && (64..=127).contains(&b)
}

pub fn parse_address(text: &str) -> Result<(Ipv4Addr, u16), String> {
    let text = text.trim();
    let (host, port) = match text.split_once(':') {
        Some((host, port)) => (
            host,
            port.parse::<u16>()
                .map_err(|_| "Use a port from 1 to 65535.")?,
        ),
        None => (text, 25565),
    };
    let ip = host
        .parse::<Ipv4Addr>()
        .map_err(|_| "Enter the host's Tailscale IPv4, such as 100.80.12.34:25565.")?;
    if !tailnet(ip) || port == 0 {
        return Err(
            "Private connections require a Tailscale IPv4 in 100.64.0.0/10 and a nonzero port."
                .into(),
        );
    }
    Ok((ip, port))
}

fn reported_ipv4(bytes: &[u8]) -> Result<Ipv4Addr, String> {
    let text =
        std::str::from_utf8(bytes).map_err(|_| "Tailscale returned an invalid IPv4 address.")?;
    let lines: Vec<_> = text
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect();
    if lines.len() != 1 {
        return Err(
            "Tailscale did not report one IPv4 address. Open Tailscale and connect first.".into(),
        );
    }
    let (ip, _) = parse_address(lines[0])?;
    // `ip -4` must return an address, not a connection endpoint supplied by some other program.
    if lines[0].contains(':') {
        return Err("Tailscale returned an invalid IPv4 address.".into());
    }
    Ok(ip)
}

pub fn tailscale_ipv4() -> Result<Ipv4Addr, String> {
    let mut candidates = Vec::<OsString>::new();
    #[cfg(target_os = "macos")]
    candidates.push(OsString::from("/Applications/Tailscale.app/Contents/MacOS/Tailscale"));
    if let Some(program_files) = env::var_os("ProgramFiles") {
        candidates.push(
            PathBuf::from(program_files)
                .join("Tailscale/tailscale.exe")
                .into_os_string(),
        );
    }
    candidates.extend([OsString::from("tailscale.exe"), OsString::from("tailscale")]);
    for candidate in candidates {
        let result = Command::new(candidate)
            .args(["ip", "-4"])
            .stdin(Stdio::null())
            .output();
        if let Ok(output) = result {
            if output.status.success() {
                return reported_ipv4(&output.stdout);
            }
        }
    }
    Err("Tailscale is unavailable or disconnected. Install/open Tailscale, connect this PC, then try again.".into())
}

fn preferred_directory(support: &Path, profile: Option<PathBuf>) -> PathBuf {
    if let Some(profile) = profile {
        let legacy = profile.join("Documents/Herspers-Server");
        if legacy.join("server.properties").is_file() {
            return legacy;
        }
    }
    support.join("servers/tailscale")
}

pub fn server_directory(support: &Path) -> PathBuf {
    preferred_directory(support, env::var_os("USERPROFILE").map(PathBuf::from))
}

fn is_link(info: &Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        info.file_attributes() & 0x400 != 0
    }
    #[cfg(not(windows))]
    {
        info.file_type().is_symlink()
    }
}

fn directory(dir: &Path) -> Result<PathBuf, String> {
    let dir = if dir.is_absolute() {
        dir.to_owned()
    } else {
        env::current_dir().map_err(|e| e.to_string())?.join(dir)
    };
    if dir
        .components()
        .any(|part| matches!(part, Component::ParentDir))
    {
        return Err("Choose a server directory without '..' components.".into());
    }
    let ancestors: Vec<_> = dir.ancestors().collect();
    for ancestor in ancestors.into_iter().rev() {
        match fs::symlink_metadata(ancestor) {
            Ok(info) if info.is_dir() && !is_link(&info) => {}
            Ok(_) => {
                return Err(format!(
                    "Server directory contains a link or non-directory: {}",
                    ancestor.display()
                ))
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                fs::create_dir(ancestor)
                    .map_err(|e| format!("Cannot create {}: {e}", ancestor.display()))?;
            }
            Err(e) => return Err(format!("Cannot inspect {}: {e}", ancestor.display())),
        }
    }
    Ok(dir)
}

fn read_optional(path: &Path) -> Result<Option<Vec<u8>>, String> {
    match fs::symlink_metadata(path) {
        Ok(info) if info.is_file() && !is_link(&info) => {}
        Ok(_) => {
            return Err(format!(
                "Expected an ordinary file, without links: {}",
                path.display()
            ))
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(format!("Cannot inspect {}: {e}", path.display())),
    }
    let mut bytes = Vec::new();
    File::open(path)
        .map_err(|e| e.to_string())?
        .take((CONFIG_LIMIT + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if bytes.len() > CONFIG_LIMIT {
        return Err(format!("Configuration exceeds 1 MiB: {}", path.display()));
    }
    Ok(Some(bytes))
}

#[cfg(windows)]
fn secure_new(path: &Path, source: Option<&Path>) -> std::io::Result<File> {
    use std::ffi::c_void;
    use std::os::windows::{ffi::OsStrExt, io::FromRawHandle};
    let Some(source) = source else {
        return OpenOptions::new().write(true).create_new(true).open(path);
    };
    #[repr(C)]
    struct SecurityAttributes {
        length: u32,
        descriptor: *mut c_void,
        inherit: i32,
    }
    #[link(name = "advapi32")]
    extern "system" {
        fn GetFileSecurityW(
            path: *const u16,
            information: u32,
            descriptor: *mut c_void,
            size: u32,
            needed: *mut u32,
        ) -> i32;
        fn SetSecurityDescriptorControl(descriptor: *mut c_void, interest: u16, value: u16) -> i32;
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn CreateFileW(
            path: *const u16,
            access: u32,
            share: u32,
            security: *const SecurityAttributes,
            creation: u32,
            attributes: u32,
            template: *mut c_void,
        ) -> *mut c_void;
    }
    let original: Vec<u16> = source
        .canonicalize()?
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let destination = path
        .parent()
        .ok_or_else(|| std::io::Error::other("Missing sidecar directory"))?
        .canonicalize()?
        .join(path.file_name().unwrap_or_default());
    let destination: Vec<u16> = destination
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let mut needed = 0;
    // Read the DACL before creating any sidecar. No file content is exposed with
    // an inherited, potentially wider ACL, even while the backup is being written.
    unsafe {
        GetFileSecurityW(original.as_ptr(), 4, std::ptr::null_mut(), 0, &mut needed);
    }
    if needed == 0 || needed > CONFIG_LIMIT as u32 {
        return Err(std::io::Error::last_os_error());
    }
    let mut descriptor = vec![0u8; needed as usize];
    if unsafe {
        GetFileSecurityW(
            original.as_ptr(),
            4,
            descriptor.as_mut_ptr().cast(),
            needed,
            &mut needed,
        )
    } == 0
    {
        return Err(std::io::Error::last_os_error());
    }
    // Protect the copied DACL from being widened by automatic parent inheritance.
    if unsafe { SetSecurityDescriptorControl(descriptor.as_mut_ptr().cast(), 0x1000, 0x1000) } == 0
    {
        return Err(std::io::Error::last_os_error());
    }
    let security = SecurityAttributes {
        length: std::mem::size_of::<SecurityAttributes>() as u32,
        descriptor: descriptor.as_mut_ptr().cast(),
        inherit: 0,
    };
    let handle = unsafe {
        CreateFileW(
            destination.as_ptr(),
            0x4000_0000,
            0,
            &security,
            1,
            0x80,
            std::ptr::null_mut(),
        )
    };
    if handle == (-1isize) as *mut c_void {
        return Err(std::io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_handle(handle) })
}

#[cfg(not(windows))]
fn secure_new(path: &Path, source: Option<&Path>) -> std::io::Result<File> {
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    if let Some(source) = source {
        options.mode(fs::metadata(source)?.permissions().mode());
    }
    options.open(path)
}

fn write_new_with_source(path: &Path, bytes: &[u8], source: Option<&Path>) -> Result<(), String> {
    let mut file = secure_new(path, source).map_err(|e| e.to_string())?;
    let result = file.write_all(bytes).and_then(|_| file.sync_all());
    drop(file);
    if let Err(error) = result {
        let _ = fs::remove_file(path);
        return Err(error.to_string());
    }
    Ok(())
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<(), String> {
    write_new_with_source(path, bytes, None)
}

fn sidecar(path: &Path, suffix: &str) -> PathBuf {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let mut name = path.file_name().unwrap_or_default().to_os_string();
    name.push(format!(
        ".{suffix}-{}-{stamp}-{}",
        std::process::id(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    path.with_file_name(name)
}

#[cfg(windows)]
fn replace(temp: &Path, destination: &Path) -> std::io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "kernel32")]
    extern "system" {
        fn ReplaceFileW(
            replaced: *const u16,
            replacement: *const u16,
            backup: *const u16,
            flags: u32,
            exclude: *mut std::ffi::c_void,
            reserved: *mut std::ffi::c_void,
        ) -> i32;
    }
    let path: Vec<u16> = destination
        .canonicalize()?
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let staged: Vec<u16> = temp
        .canonicalize()?
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    // Both paths are ordinary files in the validated server directory. ReplaceFileW
    // replaces atomically on Windows while preserving the original file's permissions.
    let ok = unsafe {
        ReplaceFileW(
            path.as_ptr(),
            staged.as_ptr(),
            std::ptr::null(),
            0,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        )
    };
    if ok == 0 {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
fn replace(temp: &Path, destination: &Path) -> std::io::Result<()> {
    fs::rename(temp, destination)
}

fn write_configuration(
    path: &Path,
    original: Option<&[u8]>,
    revised: &[u8],
) -> Result<Option<PathBuf>, String> {
    if revised.len() > CONFIG_LIMIT {
        return Err("Revised configuration would exceed 1 MiB; original was preserved.".into());
    }
    let Some(original) = original else {
        write_new(path, revised)?;
        return Ok(None);
    };
    if read_optional(path)?.as_deref() != Some(original) {
        return Err(
            "Configuration changed while preparing it. Stop the old server and retry.".into(),
        );
    }
    let backup = sidecar(path, "before-tailscale.bak");
    let permissions = fs::metadata(path).map_err(|e| e.to_string())?.permissions();
    write_new_with_source(&backup, original, Some(path))?;
    fs::set_permissions(&backup, permissions.clone()).map_err(|e| e.to_string())?;
    let temp = sidecar(path, "tailscale.tmp");
    write_new_with_source(&temp, revised, Some(path))?;
    let result = (|| {
        fs::set_permissions(&temp, permissions).map_err(|e| e.to_string())?;
        if read_optional(path)?.as_deref() != Some(original) {
            return Err(
                "Configuration changed while preparing it. Stop the old server and retry.".into(),
            );
        }
        replace(&temp, path).map_err(|e| {
            format!(
                "Could not replace {}; original backup is {}: {e}",
                path.display(),
                backup.display()
            )
        })
    })();
    let _ = fs::remove_file(&temp);
    result?;
    Ok(Some(backup))
}

fn simple_properties<'a, const N: usize>(
    bytes: &'a [u8],
    names: [&[u8]; N],
) -> [Option<&'a [u8]>; N] {
    // Parse unambiguous literal properties using Java's natural CR/LF lines and
    // whitespace. Escaped keys/values remain unknown, while later literal values
    // still win. Continuation bodies can never masquerade as a new property.
    let mut values = [None; N];
    let (mut position, mut continuing) = (0, false);
    let trim = |line: &[u8]| {
        line.iter()
            .take_while(|&&b| matches!(b, b' ' | b'\t' | b'\x0c'))
            .count()
    };
    while position < bytes.len() {
        let start = position;
        while position < bytes.len() && !matches!(bytes[position], b'\n' | b'\r') {
            position += 1;
        }
        let line = &bytes[start..position];
        if position < bytes.len() {
            let carriage = bytes[position] == b'\r';
            position += 1;
            if carriage && bytes.get(position) == Some(&b'\n') {
                position += 1;
            }
        }
        let line = &line[trim(line)..];
        let continues = line.iter().rev().take_while(|&&b| b == b'\\').count() % 2 == 1;
        if continuing {
            continuing = continues;
            continue;
        }
        if line.is_empty() || matches!(line[0], b'#' | b'!') {
            continue;
        }
        continuing = continues;
        let end = line
            .iter()
            .position(|b| matches!(b, b'=' | b':' | b' ' | b'\t' | b'\x0c'))
            .unwrap_or(line.len());
        if line[..end].contains(&b'\\') {
            values.fill(None);
            continue;
        }
        let Some(index) = names.iter().position(|name| *name == &line[..end]) else {
            continue;
        };
        let tail = &line[end + trim(&line[end..])..];
        let tail = if matches!(tail.first(), Some(b'=' | b':')) {
            &tail[1..]
        } else {
            tail
        };
        let value = &tail[trim(tail)..];
        values[index] = (!value.contains(&b'\\')).then_some(value);
    }
    values
}

fn agreed(bytes: &[u8]) -> bool {
    simple_properties(bytes, [b"eula"])[0].is_some_and(|value| value.eq_ignore_ascii_case(b"true"))
}

pub fn configure(dir: &Path, ip: Ipv4Addr, port: u16) -> Result<Report, String> {
    if !tailnet(ip) || port == 0 {
        return Err("A private server must bind to a Tailscale IPv4 and a nonzero port.".into());
    }
    let dir = directory(dir)?;
    let config_path = dir.join("server.properties");
    let original = read_optional(&config_path)?;
    let eula_path = dir.join("eula.txt");
    let eula = read_optional(&eula_path)?;
    let block = format!("\r\n\r\n# Herspers private Tailscale server\r\nserver-ip={ip}\r\nonline-mode=false\r\nserver-port={port}\r\n");
    let old = original.as_deref().unwrap_or_default();
    let current = simple_properties(old, [b"server-ip", b"online-mode", b"server-port"]);
    let (address, port_text) = (ip.to_string(), port.to_string());
    let matches = current
        == [
            Some(address.as_bytes()),
            Some(b"false".as_slice()),
            Some(port_text.as_bytes()),
        ];
    let backup = if matches || old.ends_with(block.as_bytes()) {
        None
    } else {
        let mut revised = old.to_vec();
        revised.extend_from_slice(block.as_bytes());
        write_configuration(&config_path, original.as_deref(), &revised)?
    };
    if eula.is_none() {
        write_new(&eula_path, EULA_DEFAULT)?;
    }
    Ok(Report {
        config_path,
        backup,
        eula_agreed: eula.as_deref().is_some_and(agreed),
    })
}

/// Call only after the owner explicitly agrees to https://aka.ms/MinecraftEULA.
pub fn agree_eula(dir: &Path) -> Result<(), String> {
    let path = directory(dir)?.join("eula.txt");
    let original = read_optional(&path)?;
    if original.as_deref().is_some_and(agreed) {
        return Ok(());
    }
    let mut revised = original.as_deref().unwrap_or_default().to_vec();
    revised.extend_from_slice(b"\r\n\r\n# EULA accepted by the server owner\r\neula=true\r\n");
    write_configuration(&path, original.as_deref(), &revised)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Scratch(PathBuf);
    impl Scratch {
        fn new() -> Self {
            let path = sidecar(&env::temp_dir().join("herspers-private-server"), "test");
            fs::create_dir(&path).unwrap();
            Self(fs::canonicalize(path).unwrap())
        }
    }
    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn ip() -> Ipv4Addr {
        Ipv4Addr::new(100, 80, 12, 34)
    }

    #[test]
    fn addresses_are_tailnet_only_with_explicit_or_default_port() {
        assert_eq!(parse_address(" 100.80.12.34 ").unwrap(), (ip(), 25565));
        assert_eq!(parse_address("100.80.12.34:25566").unwrap(), (ip(), 25566));
        for host in [
            "127.0.0.1",
            "0.0.0.0",
            "192.168.1.5",
            "8.8.8.8",
            "100.63.255.255",
            "100.128.0.1",
            "100.80.12.34:0",
            "100.80.12.34:65536",
            "100.80.12.34:1:2",
            "example.com",
            "::1",
        ] {
            assert!(parse_address(host).is_err(), "{host}");
        }
        assert!(parse_address("100.64.0.1").is_ok());
        assert!(parse_address("100.127.255.254").is_ok());
    }

    #[test]
    fn cli_address_output_must_be_one_actual_tailnet_ipv4() {
        assert_eq!(reported_ipv4(b"100.80.12.34\r\n").unwrap(), ip());
        for text in [
            &b""[..],
            b"100.80.12.34\n100.90.1.2\n",
            b"100.80.12.34:123",
            b"not connected",
            b"192.168.1.2",
        ] {
            assert!(reported_ipv4(text).is_err());
        }
    }

    #[test]
    fn existing_settings_worlds_and_consent_survive_private_overrides() {
        let scratch = Scratch::new();
        let original = b"# My world\r\nlevel-name=survival\r\nmotd=Caf\xe9\r\nonline-mode=true\r\nserver-ip=\r\nserver-port=25566\r\n";
        fs::write(scratch.0.join("server.properties"), original).unwrap();
        fs::write(scratch.0.join("eula.txt"), b"eula=true\r\n").unwrap();
        fs::create_dir(scratch.0.join("survival")).unwrap();
        fs::write(scratch.0.join("survival/level.dat"), b"world data").unwrap();
        let report = configure(&scratch.0, ip(), 25565).unwrap();
        assert!(report.eula_agreed);
        assert_eq!(fs::read(report.backup.unwrap()).unwrap(), original);
        let revised = fs::read(report.config_path).unwrap();
        assert!(revised.starts_with(original));
        assert!(revised
            .ends_with(b"server-ip=100.80.12.34\r\nonline-mode=false\r\nserver-port=25565\r\n"));
        assert_eq!(
            fs::read(scratch.0.join("survival/level.dat")).unwrap(),
            b"world data"
        );
        assert_eq!(
            fs::read(scratch.0.join("eula.txt")).unwrap(),
            b"eula=true\r\n"
        );
    }

    #[test]
    fn defaults_do_not_accept_eula_and_repeat_configuration_is_idempotent() {
        let scratch = Scratch::new();
        let dir = scratch.0.join("new/server");
        let first = configure(&dir, ip(), 25565).unwrap();
        assert!(!first.eula_agreed);
        assert!(first.backup.is_none());
        let bytes = fs::read(&first.config_path).unwrap();
        let before = fs::metadata(&first.config_path)
            .unwrap()
            .modified()
            .unwrap();
        let second = configure(&dir, ip(), 25565).unwrap();
        assert!(second.backup.is_none());
        assert_eq!(fs::read(second.config_path).unwrap(), bytes);
        assert_eq!(
            fs::metadata(first.config_path).unwrap().modified().unwrap(),
            before
        );
        assert!(!agreed(&fs::read(dir.join("eula.txt")).unwrap()));
    }

    #[test]
    fn canonical_native_settings_are_not_rewritten_without_a_managed_footer() {
        let scratch = Scratch::new();
        let bytes = b"# Generated by server\nonline-mode=false\nrcon.password=C:\\private\\value\nserver-ip=100.80.12.34\nserver-port=25565\n";
        fs::write(scratch.0.join("server.properties"), bytes).unwrap();
        let report = configure(&scratch.0, ip(), 25565).unwrap();
        assert!(report.backup.is_none());
        assert_eq!(fs::read(report.config_path).unwrap(), bytes);
    }

    #[test]
    fn a_later_wrong_duplicate_or_a_continuation_body_is_not_trusted() {
        for bytes in [&b"online-mode=false\nserver-ip=100.80.12.34\nserver-port=25565\nonline-mode=true\n"[..],
                      b"online-mode=true\nmotd=continued\\\r\nonline-mode=false\r\nserver-ip=100.80.12.34\r\nserver-port=25565\r\n"] {
            let scratch = Scratch::new();
            fs::write(scratch.0.join("server.properties"), bytes).unwrap();
            let report = configure(&scratch.0, ip(), 25565).unwrap();
            assert!(report.backup.is_some());
            assert!(fs::read(report.config_path).unwrap().ends_with(b"online-mode=false\r\nserver-port=25565\r\n"));
        }
    }

    #[test]
    fn explicit_consent_remains_readable_after_earlier_escaped_properties() {
        let scratch = Scratch::new();
        fs::write(
            scratch.0.join("eula.txt"),
            b"note=C:\\private\\file\r\neula=tr\\\r\nue\r\neula=false",
        )
        .unwrap();
        agree_eula(&scratch.0).unwrap();
        let bytes = fs::read(scratch.0.join("eula.txt")).unwrap();
        assert!(agreed(&bytes));
        let count = fs::read_dir(&scratch.0).unwrap().count();
        agree_eula(&scratch.0).unwrap();
        assert_eq!(fs::read_dir(&scratch.0).unwrap().count(), count);
    }

    #[test]
    fn oversized_revised_config_preserves_original_without_sidecars() {
        let scratch = Scratch::new();
        let bytes = vec![b'#'; CONFIG_LIMIT];
        fs::write(scratch.0.join("server.properties"), &bytes).unwrap();
        assert!(configure(&scratch.0, ip(), 25565)
            .unwrap_err()
            .contains("exceed 1 MiB"));
        assert_eq!(
            fs::read(scratch.0.join("server.properties")).unwrap(),
            bytes
        );
        assert_eq!(fs::read_dir(&scratch.0).unwrap().count(), 1);
    }

    #[cfg(unix)]
    #[test]
    fn private_config_modes_survive_backup_and_replacement() {
        use std::os::unix::fs::PermissionsExt;
        let scratch = Scratch::new();
        let path = scratch.0.join("server.properties");
        fs::write(&path, b"online-mode=true\nrcon.password=private\n").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        let report = configure(&scratch.0, ip(), 25565).unwrap();
        assert_eq!(
            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(
            fs::metadata(report.backup.unwrap())
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }

    #[test]
    fn explicit_eula_agreement_preserves_original_and_does_not_repeat_edits() {
        let scratch = Scratch::new();
        let original = b"# User file\r\neula=false\r\n";
        fs::write(scratch.0.join("eula.txt"), original).unwrap();
        agree_eula(&scratch.0).unwrap();
        let entries: Vec<_> = fs::read_dir(&scratch.0)
            .unwrap()
            .map(|e| e.unwrap().path())
            .collect();
        assert_eq!(entries.len(), 2);
        let backup = entries
            .iter()
            .find(|p| p.file_name().unwrap() != "eula.txt")
            .unwrap();
        assert_eq!(fs::read(backup).unwrap(), original);
        let accepted = fs::read(scratch.0.join("eula.txt")).unwrap();
        assert!(agreed(&accepted));
        agree_eula(&scratch.0).unwrap();
        assert_eq!(fs::read(scratch.0.join("eula.txt")).unwrap(), accepted);
        assert_eq!(fs::read_dir(&scratch.0).unwrap().count(), 2);
    }

    #[test]
    fn eula_parser_is_conservative_and_last_simple_property_wins() {
        assert!(agreed(b"! a comment\n eula : TRUE\n"));
        for bytes in [
            &b"#eula=true\neula=false\n"[..],
            b"eula=true\neula=false",
            b"eula=true ",
            b"eula=true #comment",
            b"eula=true\n\\u0065ula=false",
            b"eula=tr\\\nue",
            b"\x0beula=true",
            b"eula=true\nx=foo\reula=false",
        ] {
            assert!(!agreed(bytes), "{:?}", bytes);
        }
    }

    #[test]
    fn appended_blank_line_breaks_an_existing_properties_continuation() {
        let scratch = Scratch::new();
        fs::write(scratch.0.join("server.properties"), b"motd=hello\\").unwrap();
        let report = configure(&scratch.0, ip(), 25565).unwrap();
        assert!(fs::read(report.config_path)
            .unwrap()
            .starts_with(b"motd=hello\\\r\n\r\n# Herspers"));
    }

    #[test]
    fn invalid_bind_or_port_does_not_create_a_server_directory() {
        let scratch = Scratch::new();
        let dir = scratch.0.join("not-created");
        assert!(configure(&dir, Ipv4Addr::UNSPECIFIED, 25565).is_err());
        assert!(configure(&dir, ip(), 0).is_err());
        assert!(!dir.exists());
    }

    #[test]
    fn occupied_configuration_path_and_stale_edits_are_preserved() {
        let scratch = Scratch::new();
        fs::create_dir(scratch.0.join("server.properties")).unwrap();
        assert!(configure(&scratch.0, ip(), 25565).is_err());
        assert!(!scratch.0.join("eula.txt").exists());
        let path = scratch.0.join("changed.properties");
        fs::write(&path, b"new user content").unwrap();
        assert!(write_configuration(&path, Some(b"old content"), b"replacement").is_err());
        assert_eq!(fs::read(path).unwrap(), b"new user content");
    }

    #[test]
    fn ordinary_user_backup_files_are_not_overwritten() {
        let scratch = Scratch::new();
        fs::write(scratch.0.join("server.properties"), b"online-mode=true\n").unwrap();
        let existing = scratch.0.join("server.properties.before-tailscale.bak");
        fs::write(&existing, b"keep my backup").unwrap();
        let report = configure(&scratch.0, ip(), 25565).unwrap();
        assert_ne!(report.backup.as_deref(), Some(existing.as_path()));
        assert_eq!(fs::read(existing).unwrap(), b"keep my backup");
    }

    #[test]
    fn legacy_server_is_preferred_only_when_its_configuration_exists() {
        let scratch = Scratch::new();
        let support = scratch.0.join("support");
        assert_eq!(
            preferred_directory(&support, Some(scratch.0.clone())),
            support.join("servers/tailscale")
        );
        let legacy = scratch.0.join("Documents/Herspers-Server");
        fs::create_dir_all(&legacy).unwrap();
        fs::write(legacy.join("server.properties"), b"level-name=my-world").unwrap();
        assert_eq!(
            preferred_directory(&support, Some(scratch.0.clone())),
            legacy
        );
    }

    #[cfg(unix)]
    #[test]
    fn symlinked_files_and_parent_directories_are_refused() {
        use std::os::unix::fs::symlink;
        let scratch = Scratch::new();
        let target = scratch.0.join("original");
        fs::write(&target, b"private data").unwrap();
        symlink(&target, scratch.0.join("server.properties")).unwrap();
        assert!(configure(&scratch.0, ip(), 25565).is_err());
        assert_eq!(fs::read(&target).unwrap(), b"private data");
        fs::remove_file(scratch.0.join("server.properties")).unwrap();
        symlink(&scratch.0, scratch.0.join("linked")).unwrap();
        assert!(configure(&scratch.0.join("linked/server"), ip(), 25565).is_err());
        assert!(!scratch.0.join("server").exists());
    }
}
