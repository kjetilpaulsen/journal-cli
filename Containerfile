# journal-cli image for rootless Podman: podman build -t journal-cli .
# The container only idles. `bin/journal` starts the TUI inside it with `podman exec`, so
# opening the journal never waits for a container to boot.

ARG PYTHON_IMAGE=docker.io/library/python:3.14-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.9

FROM ${UV_IMAGE} AS uv

# -- build: resolve the locked dependencies and install the project into /opt/venv ---------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# -- runtime -------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE}

# Same fixed uid as journal-service; the Quadlet unit maps it to your host user (keep-id),
# so this container can use the service's 0600 socket.
RUN groupadd --system --gid 10001 journal \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin journal \
 && install -d -m 0700 -o 10001 -g 10001 \
        /xdg/config/journal-cli /xdg/state/journal-cli /xdg/runtime/journal-service

COPY --from=build /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CONFIG_HOME=/xdg/config \
    XDG_STATE_HOME=/xdg/state \
    XDG_RUNTIME_DIR=/xdg/runtime

USER 10001:10001
ENTRYPOINT ["journal-cli"]
CMD ["idle"]
