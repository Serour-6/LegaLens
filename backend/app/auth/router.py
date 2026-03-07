import logging

from fastapi import APIRouter, Depends

from app.auth.schemas import UserOut
from app.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
async def get_me(user: dict = Depends(get_current_user)):
    logger.info("User signed in successfully: %s (%s)", user["email"], user["user_id"])
    return UserOut(user_id=user["user_id"], email=user["email"])
