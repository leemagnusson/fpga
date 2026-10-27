# syntax=docker/dockerfile:1
#
# Docker image for running Vivado in CI. Build it with ci/docker/build.sh and
# run Vivado through ci/vivado.sh.
#
# Two targets:
#   runtime (default) - Ubuntu 24.04 plus the libraries Vivado needs. Vivado
#                       itself is bind-mounted from the host at run time, so
#                       the image is small and nothing licensed is baked in.
#   web               - the same, with a minimal Vivado (Artix-7 only, about
#                       20 GB) installed from the AMD web installer during the
#                       build by ci/vivado-install/install.sh, for a runner
#                       that should keep Vivado inside Docker. Needs the
#                       installer .bin and an AMD auth token; see build.sh --web.
#
# Ubuntu 24.04 is a version Vivado recognises, so it uses its own bundled
# libncurses.so.5 and the start-up failure seen on newer Ubuntu goes away.

FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        locales \
        libfontconfig1 \
        libfreetype6 \
        libgl1 \
        libglib2.0-0t64 \
        libgomp1 \
        libice6 \
        libnss3 \
        libpixman-1-0 \
        libsm6 \
        libx11-6 \
        libxext6 \
        libxft2 \
        libxi6 \
        libxrender1 \
        libxtst6 \
    && rm -rf /var/lib/apt/lists/* \
    && locale-gen en_US.UTF-8

# Vivado's launcher requires en_US.UTF-8 and aborts with
# "locale::facet::_S_create_c_locale name not valid" without it.
ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# Tells go.tcl to skip board programming.
ENV CI=true

CMD ["bash"]

# ---------------------------------------------------------------------------
FROM runtime AS web

ARG VIVADO_VERSION=2026.1
ARG INSTALLER
ARG DEVICES="Artix-7 FPGAs"

# The web installer .bin comes from a named build context ("installer", the
# directory holding it) and the AMD download token from a BuildKit secret, so
# neither ends up in an image layer. ip is needed for the host-ID hint only.
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*
COPY ci/vivado-install/install.sh /tmp/vivado-install.sh
RUN --mount=type=bind,from=installer,target=/mnt/installer \
    --mount=type=secret,id=xilinx_auth,target=/root/.Xilinx/wi_authentication_key \
    /tmp/vivado-install.sh --installer "/mnt/installer/${INSTALLER}" \
        --dest /opt/Xilinx --devices "${DEVICES}" --no-libs \
    && rm -rf /root/.Xilinx/install_config_* /opt/Xilinx/.xinstall/*/data/images \
    && rm /tmp/vivado-install.sh

ENV XILINX_VIVADO=/opt/Xilinx/${VIVADO_VERSION}/Vivado
ENV PATH=/opt/Xilinx/${VIVADO_VERSION}/Vivado/bin:${PATH}
