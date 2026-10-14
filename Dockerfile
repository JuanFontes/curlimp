# syntax=docker/dockerfile:1
# Ready-to-run release runtime. Override RUNTIME_IMAGE to use a local build.
# Maintainers build the runtime with docker/Dockerfile.build.
ARG RUNTIME_IMAGE=juanfontes/curlimp:0.3.1@sha256:39d0e1a35be64e3ef54cd536f49aded6593927aa3fadc23a49460a711cc4d988
FROM ${RUNTIME_IMAGE}
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/curlimp"]
CMD ["--help"]
