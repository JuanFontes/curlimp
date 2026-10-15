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
    assert_eq!(c.outputs, ["out.bin"]);
    assert_eq!(c.urls[0], "https://httpbin.org/get");
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
    assert_eq!(parse(vec![]).unwrap(), Action::Help);
    assert_eq!(parse(vec!["--help".into()]).unwrap(), Action::Help);
    assert_eq!(parse(vec!["--version".into()]).unwrap(), Action::Version);
    assert_eq!(
        parse(vec!["--list-profiles".into()]).unwrap(),
        Action::Profiles
    );
}

#[test]
fn no_arguments_print_help_to_stdout_without_initializing_a_transfer() {
    for args in [vec![], vec!["--help"], vec!["-h"]] {
        let result = std::process::Command::new(env!("CARGO_BIN_EXE_curlimp"))
            .args(args)
            .env("CURL_IMPERSONATE", "invalid-profile")
            .output()
            .unwrap();
        assert!(result.status.success(), "{:?}", result.stderr);
        assert!(result.stderr.is_empty());
        let help = String::from_utf8(result.stdout).unwrap();
        assert!(help.contains("Usage: curlimp"));
        assert!(help.contains("Examples:"));
        assert!(help.contains("curlimp -I https://httpbin.org/status/200"));
    }
}

#[test]
fn nonempty_commands_without_a_url_still_fail() {
    for args in [
        vec!["-I"],
        vec!["--"],
        vec!["--json-output"],
        vec!["--impersonate", "firefox147"],
        vec!["firefox147"],
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
fn multiple_urls_accept_outputs_before_or_after_urls() {
    for args in [
        vec![
            "https://a.test",
            "https://b.test",
            "-o",
            "first",
            "-osecond",
        ],
        vec![
            "--output=first",
            "--url=https://a.test",
            "-o",
            "second",
            "https://b.test",
        ],
    ] {
        assert!(matches!(
            parse(args.into_iter().map(String::from).collect()),
            Ok(Action::Transfer(_))
        ));
    }
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
        assert_eq!(c.urls[0], url);
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
        assert_eq!(c.outputs, ["firefox147"]);
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
        assert!(c.urls[0].ends_with("firefox147"));
    }
    let c = transfer(&["--json", "chrome150", url]);
    assert_eq!(c.data[0].value, "chrome150");
    assert_eq!(c.impersonate, None);
}

#[test]
fn profile_shorthand_requires_one_exact_name_before_a_url() {
    let url = "https://httpbin.org/status/200";
    for args in [vec!["firefox147"], vec!["chrome150", "firefox147", url]] {
        assert_eq!(
            parse(args.into_iter().map(String::from).collect())
                .unwrap_err()
                .code,
            2
        );
    }
    // A bare hostname that is not an exact profile retains curl's URL meaning.
    assert_eq!(transfer(&["chrome15"]).urls[0], "chrome15");
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

#[test]
fn urls_and_destinations_keep_independent_order() {
    let c = transfer(&[
        "--output=first",
        "--url=https://a.test",
        "https://b.test",
        "-o-",
        "--",
        "firefox147",
    ]);
    let targets: Vec<_> = c.targets().collect();
    assert_eq!(targets[0].url, "https://a.test");
    assert_eq!(targets[0].output.as_deref(), Some("first"));
    assert_eq!(targets[1].output.as_deref(), Some("-"));
    assert_eq!(targets[2].url, "firefox147");
    assert_eq!(targets[2].output, None);
    assert_eq!(targets[2].index, 2);
}

#[test]
fn parallel_flags_accept_curl_forms_and_reject_invalid_limits() {
    for flags in [
        vec!["-ZsS"],
        vec!["--parallel-max=2", "--parallel"],
        vec!["-Z", "--no-parallel"],
        vec!["--parallel-max", "0"],
        vec!["--parallel-max", "65536"],
    ] {
        let mut args = flags;
        args.push("https://httpbin.org/status/200");
        assert!(parse(args.into_iter().map(String::from).collect()).is_ok());
    }
    for value in ["-1", "1.5", "a", "18446744073709551616"] {
        assert!(parse(
            ["--parallel-max", value, "https://httpbin.org/status/200"]
                .into_iter()
                .map(String::from)
                .collect()
        )
        .is_err());
    }
}

#[test]
fn parallel_limits_and_overrides_preserve_curl_semantics() {
    let url = "https://httpbin.org/status/200";
    for (value, expected) in [("0", 50), ("1", 1), ("65535", 65535), ("65536", 65535)] {
        let c = transfer(&["--parallel-max", value, url]);
        assert_eq!(c.parallel_max, Some(expected));
        assert!(!c.parallel);
    }
    assert!(!transfer(&["-Z", "--no-parallel", url]).parallel);
    assert!(transfer(&["--no-parallel", "-Z", url]).parallel);
}
