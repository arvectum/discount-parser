from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.qa.operational_status import build_operational_status
from src.web.processes import process_manager
from src.web.setup import is_setup_complete


router = APIRouter()


@router.get('/system/status.json', response_class=JSONResponse)
def operational_status_json():
    if not is_setup_complete():
        return JSONResponse(
            status_code=409,
            content={
                'schema_version': 1,
                'state': 'warning',
                'reasons': ['setup_incomplete'],
                'setup_complete': False,
            },
        )
    return JSONResponse(
        content=build_operational_status(process_states=process_manager.states())
    )
