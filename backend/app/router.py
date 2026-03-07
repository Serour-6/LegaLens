from fastapi import APIRouter

from app.routes import documents

router = APIRouter(prefix="/api")

router.include_router(documents.router)
