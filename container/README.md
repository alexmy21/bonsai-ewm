# Running bonsai-ewm in a container

The controller ships as a small image: Python (stdlib only) + the
`ewm-scene` binary. Bonsai itself is **not baked in** — it runs on the GPU
host (or in a sidecar container) and the controller reaches it over HTTP.
This keeps the image small and the model out of the OCI layer.

## Build

Local build (context = the directory that contains both repos):

```bash
cd /home/alexmy/SGS/SGS_lib/fractal_manifold_gen2
podman build --format docker \
  --ignorefile bonsai-ewm/container/.containerignore \
  --build-arg EWM_SM_SRC=ewm-state-machine \
  --build-arg CONTROLLER_SRC=bonsai-ewm \
  -f bonsai-ewm/container/Containerfile \
  -t bonsai-ewm .
```

The `--format docker` keeps the HEALTHCHECK instruction (podman's default
OCI format would drop it). The `--ignorefile` keeps the 23 GB
parent-directory context down to the two source trees the build actually
needs (`cargo target/` dirs and sibling projects are excluded).

Build from a git URL instead of a local directory — clone the repo next to
bonsai-ewm first, then use the same local build:

```bash
cd /home/alexmy/SGS/SGS_lib/fractal_manifold_gen2
git clone https://github.com/<you>/ewm-state-machine.git ewm-state-machine
podman build --format docker \
  --ignorefile bonsai-ewm/container/.containerignore \
  --build-arg EWM_SM_SRC=ewm-state-machine \
  --build-arg CONTROLLER_SRC=bonsai-ewm \
  -f bonsai-ewm/container/Containerfile \
  -t bonsai-ewm .
```

## Run

With the Bonsai server on the host (started by
`bonsai-ewm/scripts/start_bonsai_server.sh` on port 8081):

```bash
podman run --rm -it \
  -e BONSAI_URL=http://host.containers.internal:8081 \
  bonsai-ewm
```

`BONSAI_URL` can point at a sidecar container instead:

```bash
podman run -d --name bonsai-server --network bonsai-net \
  -e BONSAI_PORT=8081 -p 8081:8081 \
  <your-bonsai-server-image>

podman run --rm -it --network bonsai-net \
  -e BONSAI_URL=http://bonsai-server:8081 \
  bonsai-ewm
```

## Health check

The image carries a Docker/podman HEALTHCHECK that runs
`bonsai-ewm --health` every 30 s: it verifies the `ewm-scene` binary, the
work dir, and the reachability of `BONSAI_URL`, and reports the result as
JSON:

```bash
podman run --rm bonsai-ewm --health
```

## What is deliberately out of the image

- **Bonsai weights** (~7.2 GB): mounted or fetched at runtime; the
  PrismML llama.cpp fork needs its own CUDA build, which is host-GPU
  territory, not controller territory.
- **The ewm-state-machine source**: only the compiled `ewm-scene` binary
  is copied in.

## Image contents

```text
/usr/local/bin/ewm-scene      # the lattice apparatus
/usr/local/bin/bonsai-ewm     # the console script (entrypoint)
/var/lib/bonsai-ewm           # session work dir (saved sessions too)
```
