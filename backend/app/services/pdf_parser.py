import io
import logging
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Parses a PDF file from bytes and returns all extracted text.
    """
    pdf_stream = io.BytesIO(file_bytes)
    reader = PdfReader(pdf_stream)

    extracted_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            extracted_text.append(text)

    full_text = "\n".join(extracted_text)
    logger.info("Extracted text from PDF (%s pages)", len(reader.pages))

    return full_text