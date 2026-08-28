from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.services import results_service

router = APIRouter(prefix="/results", tags=["results"])


@router.get("")
def list_results():
    """Dashboard summary: model x benchmark matrix of primary scores."""
    return {
        "models": results_service.list_models(),
        "matrix": results_service.dashboard_matrix(),
    }


@router.get("/load_testing")
def list_load_testing_results():
    """Latest model load-test measurements, grouped client-side for comparison."""
    return {"results": results_service.load_testing_results()}


@router.get("/{model}")
def get_model_results(model: str):
    results = results_service.results_for_model(model)
    if not results:
        raise HTTPException(status_code=404, detail=f"No results found for model '{model}'")
    return {"model": model, "results": results}


@router.get("/{model}/{benchmark}")
def get_detailed_result(model: str, benchmark: str):
    result = results_service.detailed_result(model, benchmark)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No result found for model '{model}' on benchmark '{benchmark}'",
        )
    return result

@router.delete("/load_testing/{model}/{provider}/{concurrent_users}")
def delete_load_testing_result(model: str, provider: str, concurrent_users: int, timestamp: str):
    if not results_service.delete_load_testing_result(model, provider, concurrent_users, timestamp):
        raise HTTPException(status_code=404, detail="Result not found")
    return {"deleted": True}


@router.delete("/{model}/{benchmark}")
def delete_detailed_result(model: str, benchmark: str, timestamp: str | None = Query(default=None)):
    if not results_service.delete_latest_result(model, benchmark, timestamp):
        raise HTTPException(status_code=404, detail="Result not found")
    return {"deleted": True}
