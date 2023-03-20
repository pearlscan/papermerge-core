import logging
from pathlib import PurePosixPath

import numpy as np
from PIL import Image

from pydicom import dcmread
from pydicom.dataset import Dataset, FileDataset
from pydicom.dataelem import DataElement
from pydicom.sequence import Sequence

from typing import Union


logger = logging.getLogger(__name__)


def dicom_to_dict(ds: Union[Dataset, FileDataset, str]) -> dict:
    if isinstance(ds, str):
        ds = dcmread(ds)

    result = {}

    for element in ds:
        if isinstance(element, DataElement):
            key = element.name
            value = element.value

            if not value:
                continue

            if key in ('Pixel Data', 'Private tag data'):
                continue

            if isinstance(value, Sequence):
                value = [dicom_to_dict(item) for item in value]

            result[key] = str(value)

    return result


def dicom_to_pdf(ds: Union[Dataset, FileDataset], output_path: str):
    # Get the pixel data as a numpy array
    pixel_array = ds.pixel_array

    # Normalize the pixel data to 8-bit (0-255) for JPEG
    min_val = np.min(pixel_array)
    max_val = np.max(pixel_array)
    normalized_array = ((pixel_array - min_val) / (max_val - min_val)) * 255

    # Convert the normalized pixel data to an 8-bit unsigned integer numpy array
    uint8_array = normalized_array.astype(np.uint8)

    # Create a PIL Image object from the numpy array
    image = Image.fromarray(uint8_array)

    # Save the image as a PDF file
    image.save(output_path)


def convert_dicom2pdf(doc_url) -> str:
    logger.debug(f"convert_tiff2pdf for {doc_url}")

    doc_path = PurePosixPath(doc_url)
    new_doc_url = doc_path.with_suffix(".pdf")
    new_filename = new_doc_url.name

    logger.debug(
        f"dicom2pdf source={doc_url} dest={new_doc_url}"
    )

    ds = dcmread(doc_url)
    dicom_to_pdf(ds, str(new_doc_url))

    return str(new_filename)
