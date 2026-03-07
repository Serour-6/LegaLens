from fastapi import APIRouter, UploadFile, HTTPException, Depends

from app.auth.dependencies import get_current_user
from app.services.pdf_parser import extract_text_from_pdf

router = APIRouter(prefix="/services", tags=["services"])


@router.post("/parse-pdf")
async def parse_pdf(file: UploadFile, user: dict = Depends(get_current_user)):
    """Extract text from an uploaded PDF without storing it."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    contents = await file.read()
    extracted_text = extract_text_from_pdf(contents)
    return {"extracted_text": extracted_text}
