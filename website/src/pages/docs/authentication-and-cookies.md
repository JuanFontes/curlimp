---
layout: ../../layouts/Doc.astro
title: 'Authentication and cookies'
description: 'Use HTTP Basic authentication, bearer request headers, cookies and persistent cookie jars with curlimp and Docker.'
slug: authentication-and-cookies
section: Usage
lead: 'Send explicit credentials and cookie state. Profiles do not provide a browser login session.'
---

## HTTP Basic authentication

Pass the username and password after `-u`:

```sh
curlimp -sS -I -u 'demo:demo-password' https://httpbin.org/status/200
```

The status endpoint does not authenticate this sample account. This example demonstrates how to supply credentials. Use only credentials intended for the destination service.

Do not put `username:password` between flags and the URL without `-u`; the parser treats it as another positional URL. Interactive password prompting and `.netrc` are not supported.

## Bearer tokens

Set the Authorization header explicitly:

```sh
curlimp -sS -I -H 'Authorization: Bearer demo-token' \
  https://httpbin.org/status/200
```

`demo-token` is a placeholder, not a functioning credential. Debug logs, shell history and process listings can expose real secrets. Keep them out of shared command output and issue reports.

## Send cookie values

`-b` accepts a cookie string; repeat it for additional values:

```sh
curlimp -sS -I -b 'theme=dark; mode=demo' https://httpbin.org/status/200
```

The status fixture does not echo the cookies. A real application decides whether a cookie is valid.

## Read and write a cookie jar

Use a host-mounted path so a jar survives a disposable Docker container:

```sh
docker run --rm -v "$PWD:/work" juanfontes/curlimp:latest \
  -sS -b /work/cookies.txt -c /work/cookies.txt \
  https://httpbin.org/status/200
```

Start with a cookie file in libcurl's supported format, or use `-c` alone when collecting cookies from a response. A cookie jar is populated only if the server actually sets cookies; the status fixture may leave it empty apart from file comments. Persistence also depends on the mounted directory being writable.

For a native binary:

```sh
curlimp -sS -b cookies.txt -c cookies.txt \
  https://httpbin.org/status/200
```

Cookie options do not execute a website's JavaScript, create local storage, or reproduce a browser authentication flow. See [compatibility](../compatibility/) for scope.
