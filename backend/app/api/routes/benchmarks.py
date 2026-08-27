from __future__ import annotations

from fastapi import APIRouter

from backend.app.services import benchmarks_service

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("")
def list_benchmarks():
    return {"benchmarks": benchmarks_service.list_benchmarks()}
