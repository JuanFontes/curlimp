# syntax=docker/dockerfile:1
# Ready-to-run release runtime. Override RUNTIME_IMAGE to use a local build.
# Maintainers build the runtime with docker/Dockerfile.build.
ARG RUNTIME_IMAGE=juanfontes/curlimp:0.3.0@sha256:8ceb91d1232accfeeff90d4e02a79bcf20fc05a8fae23cd04ad9aa277df176d3
FROM ${RUNTIME_IMAGE}
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/curlimp"]
CMD ["--help"]
