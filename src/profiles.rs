/// The release's catalog, shared by parsing, listing, and shell completion.
pub fn names() -> impl Iterator<Item = &'static str> {
    include_str!("profiles.txt")
        .lines()
        .map(str::trim)
        .filter(|name| !name.is_empty() && !name.starts_with('#'))
}

pub fn contains(name: &str) -> bool {
    names().any(|candidate| candidate == name)
}

/// Reject the retired native target and alias; other aliases stay engine-owned.
pub fn validate(profile: &str) -> Result<(), crate::cli::CliError> {
    let name = profile.split(':').next().unwrap_or(profile);
    if name.eq_ignore_ascii_case("okhttp4_android") || name.eq_ignore_ascii_case("okhttp4") {
        return Err(crate::cli::CliError::new(
            2,
            "the unverified, inconsistent OkHttp profile has been retired",
        ));
    }
    Ok(())
}
