from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.document import HealthResponse
from fastapi import Depends

from app.core.logging import get_logger
from app.services.ai.groq_client import groq_client

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health + capability probe")
def health(db: Session = Depends(get_db)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        groq_connected=groq_client.available,
        ocr_provider=settings.OCR_PROVIDER,
    )
