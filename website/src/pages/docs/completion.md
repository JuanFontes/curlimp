---
layout: ../../layouts/Doc.astro
title: 'Zsh profile autocomplete'
description: 'Complete Curlimp browser profiles with Tab in Zsh. Match any profile prefix, choose from a menu, and keep editing your request.'
slug: completion
section: Usage
lead: 'Type a little or a lot of a profile name. Tab matches everything you have typed.'
---

## Enable completion

Install the native `curlimp` command on your `PATH`, then add this after your existing completion setup in `~/.zshrc`:

```zsh
# Initialize completion only if your shell configuration does not already do it.
autoload -Uz compinit
compinit
source <(curlimp --completions zsh)

# Optional: open a selection menu on Tab for this command.
zstyle ':completion:*:curlimp:*' menu yes select
```

Open a new terminal or run these lines in your current Zsh session. `--completions zsh` prints the integration script; it does not change your shell configuration or make an HTTP request.

The Rust CLI reads the shared profile catalog and filters candidates. Zsh handles the Tab key, displays the choices, and inserts the selected name before the command runs.

## Match any prefix

Type `curlimp ` and press Tab to show all available profiles. With the optional menu enabled, use Tab or the arrow keys to choose, then Enter to accept the selection and continue editing. A second Enter executes the finished command. Custom Zsh key bindings can change these keys.

| Text before Tab      | Matching names                             |
| -------------------- | ------------------------------------------ |
| `curlimp c`          | All Chrome profiles                        |
| `curlimp chrome1`    | Chrome names starting with `chrome1`       |
| `curlimp chrome15`   | `chrome150`                                |
| `curlimp chrome131_` | `chrome131_android`                        |
| `curlimp firefox14`  | `firefox144`, `firefox147`                 |
| `curlimp safari26`   | `safari260`, `safari2601`, `safari260_ios` |

There is no minimum or maximum prefix length. Matching is literal and case-sensitive for every profile family. An unknown prefix produces no suggestions. Executing a partial name does not expand it: use Tab to insert a complete name before running the command.

## Add the rest of your request

Flags can appear before or after the profile, which must come before the URL:

```sh
curlimp firefox147 -sS -I https://httpbin.org/status/200
curlimp -sS safari2601 -i https://httpbin.org/status/418
curlimp chrome150 -sS -o /dev/null -w '%{http_code}\n' https://httpbin.org/status/502
```

Completion also works after `--impersonate ` and `--impersonate=`. It does not suggest profiles as values for other flags or after `--`. After the URL, only an explicit `--impersonate` option can request profile suggestions. This first version completes profiles only; it does not complete flags, URLs or filenames.

## Use the bundled completion file

Native downloads also include `completions/zsh/_curlimp`. As an alternative to sourcing the generated script, copy this file into a directory on your Zsh `fpath` **before** running `compinit`. The file still asks your installed CLI for its current profile catalog.

## Docker and other shells

This first integration supports Zsh with the native executable. A Docker image cannot configure the shell on your host, and the `curli` Docker alias does not receive this completion automatically. Use the native command for the setup above. Bash and Fish integrations can be added later without duplicating the Rust matching logic.

See the [profile catalog](/curlimp/docs/profiles/) for available names and [installation instructions](/curlimp/docs/installation/) for native bundles.
