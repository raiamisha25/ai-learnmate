import fitz
import re

from utils.errors import AppError


def extract_text_from_pdf(filepath):
    """Extract readable text from a PDF file, filtering out headers, page numbers, footers, captions, and references."""
    try:
        text_parts = []
        ignore_rest = False

        with fitz.open(filepath) as doc:
            for page in doc:
                if ignore_rest:
                    break

                rect = page.rect
                height = rect.height

                # Standard margin thresholds (typically 55-60 points)
                top_margin = max(55.0, height * 0.08)
                bottom_margin = max(55.0, height * 0.08)

                blocks = page.get_text("blocks")
                # Sort blocks top-to-bottom, left-to-right to ensure reading order
                blocks.sort(key=lambda b: (b[1], b[0]))

                for b in blocks:
                    x0, y0, x1, y1, block_text, block_no, block_type = b
                    block_text_stripped = block_text.strip()
                    if not block_text_stripped:
                        continue

                    # 1. Detect and handle the end of document / References section
                    lower_text = block_text_stripped.lower()
                    if re.match(r"^\s*(references|bibliography|literature cited)\b", lower_text) and len(block_text_stripped.split()) <= 4:
                        ignore_rest = True
                        break

                    # 2. Ignore headers and footers based on coordinates and lines count
                    is_header = y0 < top_margin and len(block_text_stripped.splitlines()) <= 2
                    is_footer = y1 > (height - bottom_margin) and len(block_text_stripped.splitlines()) <= 2

                    if is_header or is_footer:
                        # Double check if it is a page number or header/footer pattern
                        if re.match(r"^\s*(page\s*)?\d+(\s*of\s*\d+)?\s*$", lower_text) or lower_text.isdigit():
                            continue
                        # If it is a short line in the header/footer margin, ignore it
                        if len(block_text_stripped.split()) <= 8:
                            continue

                    # 3. Ignore captions
                    if re.match(r"^\s*(figure|fig\.|fig|table|tab\.|tab)\s+\d+", lower_text):
                        continue

                    text_parts.append(block_text_stripped)

        text = "\n\n".join(text_parts).strip()
    except Exception as exc:
        raise AppError("This PDF could not be read. Please try another file.") from exc

    if not text:
        raise AppError("No readable text was found in this PDF.")

    return text


