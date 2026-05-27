from functools import lru_cache
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps


@lru_cache(maxsize=1)
def get_easyocr_reader():
    try:
        import easyocr
    except ImportError as exc:
        raise RuntimeError(
            "easyocr is not installed. Install OCR dependencies with requirements.txt."
        ) from exc

    return easyocr.Reader(["vi", "en"], gpu=False, verbose=False)


def image_bytes_to_text(content: bytes) -> str:
    image = Image.open(BytesIO(content))
    image = ImageOps.exif_transpose(image).convert("RGB")

    # Upscale small screenshots a bit; OCR libraries usually do better on text edges.
    width, height = image.size
    if max(width, height) < 1400:
        image = image.resize((width * 2, height * 2))

    reader = get_easyocr_reader()
    result = reader.readtext(np.array(image), detail=0, paragraph=True)
    return "\n".join(part.strip() for part in result if part and part.strip())
