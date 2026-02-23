# Deployment Guide — ANLA Notification Data Store

This document outlines the process for building, pushing, and deploying the ANLA backend to the production environment.

## 🏗 Build & Push (Local)

The deployment uses a private Docker registry hosted on Tailscale. Ensure you have access to `registry.buffalo-cliff.ts.net`.

```bash
# Navigate to the backend directory
cd backend

# Build the images (api and parser)
docker compose build

# Push the images to the private registry
docker compose push
```

## 🚀 Deploy (Remote)

The production instance is hosted at `anla-api` (via Tailscale). The deployment files are located in `~/anla`.

```bash
# SSH into the production host and update the services
ssh null@anla-api "cd ~/anla && docker compose pull && docker compose up -d"
```

## 📋 Infrastructure Summary

| Component | Image / Location |
|-----------|------------------|
| **Registry** | `registry.buffalo-cliff.ts.net` |
| **API Image** | `registry.buffalo-cliff.ts.net/anla-api:latest` |
| **Parser Image** | `registry.buffalo-cliff.ts.net/anla-parser:latest` |
| **Remote Host** | `null@anla-api` |
| **Remote Path** | `~/anla/` |

## 🛠 Troubleshooting

### Permission Denied (Docker)
If you see `permission denied while trying to connect to the docker API`, ensure your user is in the `docker` group or run the commands with `sudo`:
```bash
sudo docker compose build
sudo docker compose push
```

### SSH Connection Failed
Ensure you are connected to the **Tailscale** network and that `anla-api` is reachable.
```bash
tailscale ping anla-api
```

### Database Migrations
Migrations run automatically on container startup via `entrypoint.sh`. If you need to check migration status:
```bash
ssh null@anla-api "cd ~/anla && docker compose exec api alembic current"
```
