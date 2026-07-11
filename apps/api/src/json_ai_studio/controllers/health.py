"""Unauthenticated service metadata endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("json_ai_studio.controllers.health")

router = APIRouter()


@router.get("/health")
def health_check():
    """Health check endpoint. No auth required."""
    logger.debug("GET /health")
    return {"status": "ok", "version": "0.1.0"}


@router.get("/")
def root():
    """Root endpoint. No auth required (docs only)."""
    return {
        "service": "JSON AI Studio API",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "sessions_post": "POST /api/sessions",
            "upload": "POST /api/json/upload",
            "chat": "POST /api/chat",
            "versions_get": "GET /api/sessions/{id}/versions",
            "versions_post": "POST /api/sessions/{id}/versions",
            "versions_select": "POST /api/sessions/{id}/versions/select",
            "versions_restore": "POST /api/sessions/{id}/versions/restore",
            "diff_accept": "POST /api/sessions/{id}/diffs/{diffId}/accept",
            "diff_reject": "POST /api/sessions/{id}/diffs/{diffId}/reject",
            "diff_accept_all": "POST /api/sessions/{id}/diffs/accept-all",
            "diff_reject_all": "POST /api/sessions/{id}/diffs/reject-all",
        },
    }
