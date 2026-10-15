---
layout: ../../layouts/Doc.astro
title: 'Zsh profile autocomplete'
description: 'Complete Curlimp browser profiles with Tab in Zsh. Match any profile prefix, choose from a menu, and keep editing your request.'
slug: completion
section: Usage
lead: 'Type a little or a lot of a profile name. Tab matches everything you have typed.'
---

## Homebrew installations

`brew install juanfontes/tap/curlimp` installs the completion file in Homebrew's Zsh directory and prints a tip for activating it in the current session. Future sessions load the file automatically if your shell already loads Homebrew completions.

**Did you install Curlimp in the same terminal tab you are using now?** An existing Zsh session does not automatically register the newly installed file. Run this in the current session if completion is already initialized:

```zsh
source <(curlimp --completions zsh)
zstyle ':completion:*:curlimp:*' menu yes select
```

The first line registers Curlimp immediately. The second enables a selection menu for this command; add that `zstyle` line to `~/.zshrc` if you want to keep the preference. Neither line modifies a configuration file by itself.

If completion still does not work in a new tab, put the `fpath` line below **before any existing `compinit` call** in `~/.zshrc`. Use the whole block only if your shell does not already initialize completion:

```zsh
fpath=("$(brew --prefix)/share/zsh/site-functions" $fpath)
autoload -Uz compinit
compinit

# Optional: open a selection menu on Tab for this command.
zstyle ':completion:*:curlimp:*' menu yes select
```

The installer does not change your shell files. New sessions using this setup do not need to source the generated script separately. `brew uninstall curlimp` removes Homebrew's completion file along with the executable; restart your shell to clear loaded completion functions.

## Downloaded native bundles

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

Without the menu setting, the first Tab can insert just the shared prefix: `curlimp chrom` becomes `curlimp chrome`. Press Tab again to list the matching versions. A unique prefix such as `chrome15` completes directly to `chrome150`.

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

This first integration supports Zsh with the native executable. Running a Docker image does not configure the shell on your host. Use the native command for the setup above. Bash and Fish integrations can be added later without duplicating the Rust matching logic.

See the [profile catalog](/curlimp/docs/profiles/) for available names and [installation instructions](/curlimp/docs/installation/) for native bundles.
