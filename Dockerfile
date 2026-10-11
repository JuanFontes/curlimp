# syntax=docker/dockerfile:1
# Local development runtime. Pin the published multiarch digest at release time.
# Build this runtime with docker/Dockerfile.build before deriving this image.
ARG RUNTIME_IMAGE=curlimp:local
FROM ${RUNTIME_IMAGE}
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/curlimp"]
CMD ["--help"]
