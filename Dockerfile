# syntax=docker/dockerfile:1
# Ready-to-run release runtime. Override RUNTIME_IMAGE to use a local build.
# Maintainers build the runtime with docker/Dockerfile.build.
ARG RUNTIME_IMAGE=juanfontes/curlimp:0.5.0
FROM ${RUNTIME_IMAGE}
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/curlimp"]
CMD ["--help"]
