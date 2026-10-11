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
