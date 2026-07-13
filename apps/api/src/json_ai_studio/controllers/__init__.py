"""HTTP layer: thin FastAPI routers that delegate to services."""

from . import (
    chat,
    diffs,
    explain,
    health,
    sessions,
    uploads,
    users,
    versions,
    workspaces,
)

routers = [
    health.router,
    sessions.router,
    versions.router,
    uploads.router,
    chat.router,
    diffs.router,
    explain.router,
    users.router,
    workspaces.router,
]
