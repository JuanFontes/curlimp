use curlimp::cli::{parse, Action, Config};

fn transfer(args: &[&str]) -> Config {
    match parse(args.iter().map(|s| s.to_string()).collect()).unwrap() {
        Action::Transfer(c) => *c,
        other => panic!("expected a transfer, got {other:?}"),
    }
}

#[test]
fn clustered_flags_and_attached_values_preserve_curl_meaning() {
    let c = transfer(&[
        "-sSL",
        "-XPOST",
        "-H",
        "Accept: application/json",
        "-oout.bin",
        "https://httpbin.org/get",
    ]);
    assert!(c.silent && c.show_error && c.follow);
    assert_eq!(c.method.as_deref(), Some("POST"));
    assert_eq!(c.headers, ["Accept: application/json"]);
    assert_eq!(c.output.as_deref(), Some("out.bin"));
    assert_eq!(c.url, "https://httpbin.org/get");
}

#[test]
fn equals_values_and_fractional_timeouts_are_supported() {
    let c = transfer(&[
        "--url=https://httpbin.org/get",
        "--max-time=0.125",
        "--header=X-Test: a=b",
    ]);
    assert_eq!(c.timeout_ms, Some(125));
    assert_eq!(c.headers, ["X-Test: a=b"]);
}

#[test]
fn repeated_headers_and_data_are_not_discarded() {
    let c = transfer(&[
        "-H",
        "X-A: 1",
        "-H",
        "X-A: 2",
        "-d",
        "a=1",
        "-d",
        "b=2",
        "https://httpbin.org/get",
    ]);
    assert_eq!(c.headers, ["X-A: 1", "X-A: 2"]);
    assert_eq!(c.data.len(), 2);
}

#[test]
fn unsupported_or_incomplete_invocations_fail_before_transfer() {
    for args in [
        vec!["--retry", "2", "https://httpbin.org/get"],
        vec!["-H"],
        vec!["https://a.test", "https://b.test"],
        vec!["--max-time", "NaN", "https://httpbin.org/get"],
        vec!["--max-time", "-1", "https://httpbin.org/get"],
        vec!["--silent=yes", "https://httpbin.org/get"],
        vec!["--no-impersonate=yes", "https://httpbin.org/get"],
    ] {
        assert_eq!(
            parse(args.into_iter().map(String::from).collect())
                .unwrap_err()
                .code,
            2
        );
    }
}

#[test]
fn informational_commands_do_not_require_a_url() {
    assert_eq!(parse(vec!["--help".into()]).unwrap(), Action::Help);
    assert_eq!(parse(vec!["--version".into()]).unwrap(), Action::Version);
    assert_eq!(
        parse(vec!["--list-profiles".into()]).unwrap(),
        Action::Profiles
    );
}

#[test]
fn compression_flags_preserve_explicit_selection_and_last_value() {
    let url = "https://httpbin.org/gzip";
    assert_eq!(transfer(&[url]).compressed, None);
    assert_eq!(transfer(&["--compressed", url]).compressed, Some(true));
    assert_eq!(transfer(&["--no-compressed", url]).compressed, Some(false));
    assert_eq!(
        transfer(&["--compressed", "--no-compressed", url]).compressed,
        Some(false)
    );
    assert_eq!(
        transfer(&["--no-compressed", "--compressed", url]).compressed,
        Some(true)
    );
}

#[test]
fn positional_profile_accepts_flags_on_either_side_before_the_url() {
    let url = "https://httpbin.org/status/200";
    for args in [
        vec!["firefox147", "-sSI", url],
        vec!["-sSI", "firefox147", url],
        vec!["firefox147", url, "-sSI"],
    ] {
        let c = transfer(&args);
        assert_eq!(c.impersonate.as_deref(), Some("firefox147"));
        assert_eq!(c.url, url);
        assert!(c.silent && c.show_error && c.head);
    }
}

#[test]
fn positional_profile_obeys_last_explicit_profile_selection() {
    let url = "https://httpbin.org/status/200";
    assert!(transfer(&["firefox147", "--no-impersonate", url]).no_impersonate);
    let c = transfer(&["--no-impersonate", "firefox147", url]);
    assert!(!c.no_impersonate);
    assert_eq!(c.impersonate.as_deref(), Some("firefox147"));
    let c = transfer(&["firefox147", "--impersonate", "chrome150", url]);
    assert_eq!(c.impersonate.as_deref(), Some("chrome150"));
}

#[test]
fn option_values_and_literal_urls_are_never_positional_profiles() {
    let url = "https://httpbin.org/status/200";
    for args in [
        vec!["-o", "firefox147", url],
        vec!["-ofirefox147", url],
        vec!["--output=firefox147", url],
    ] {
        let c = transfer(&args);
        assert_eq!(c.output.as_deref(), Some("firefox147"));
        assert_eq!(c.impersonate, None);
    }
    for args in [
        vec!["--url", "firefox147"],
        vec!["--url=firefox147"],
        vec!["--", "firefox147"],
        vec!["http://firefox147"],
    ] {
        let c = transfer(&args);
        assert_eq!(c.impersonate, None);
        assert!(c.url.ends_with("firefox147"));
    }
    let c = transfer(&["--json", "chrome150", url]);
    assert_eq!(c.data[0].value, "chrome150");
    assert_eq!(c.impersonate, None);
}

#[test]
fn profile_shorthand_requires_one_exact_name_before_a_url() {
    let url = "https://httpbin.org/status/200";
    for args in [
        vec!["firefox147"],
        vec!["chrome15", url],
        vec![url, "firefox147"],
        vec!["chrome150", "firefox147", url],
    ] {
        assert_eq!(
            parse(args.into_iter().map(String::from).collect())
                .unwrap_err()
                .code,
            2
        );
    }
    // A bare hostname that is not an exact profile retains curl's URL meaning.
    assert_eq!(transfer(&["chrome15"]).url, "chrome15");
}

#[test]
fn export_modes_accept_response_selection_and_request_json() {
    for mode in ["--txt", "--json-output", "--json-file"] {
        let c = transfer(&[
            mode,
            "-i",
            "--json",
            "{\"message\":\"hello\"}",
            "https://httpbin.org/status/200",
        ]);
        assert!(c.include);
        assert_eq!(c.data.len(), 1);
    }
}

#[test]
fn export_conflicts_fail_before_transfer() {
    for mode in ["--txt", "--json-output", "--json-file"] {
        for args in [
            vec![mode, "-o", "out"],
            vec![mode, "-D", "headers"],
            vec![mode, "-w", "%{http_code}"],
        ] {
            let mut args = args;
            args.push("https://httpbin.org/status/200");
            assert_eq!(
                parse(args.into_iter().map(String::from).collect())
                    .unwrap_err()
                    .code,
                2
            );
        }
    }
    for pair in [
        ["--txt", "--json-output"],
        ["--txt", "--json-file"],
        ["--json-output", "--json-file"],
        ["--json-output", "-N"],
    ] {
        assert!(parse(
            [pair[0], pair[1], "https://httpbin.org/status/200"]
                .into_iter()
                .map(String::from)
                .collect()
        )
        .is_err());
    }
    assert!(parse(
        ["--txt", "--txt", "-N", "https://httpbin.org/status/200"]
            .into_iter()
            .map(String::from)
            .collect()
    )
    .is_ok());
}
