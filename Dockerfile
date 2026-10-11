# syntax=docker/dockerfile:1
# Ready-to-run release runtime. Override RUNTIME_IMAGE to use a local build.
# Build this runtime with docker/Dockerfile.build before deriving this image.
ARG RUNTIME_IMAGE=juanfontes/curlimp:0.3.0
FROM ${RUNTIME_IMAGE}
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/curlimp"]
CMD ["--help"]
