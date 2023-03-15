import os
import logging
import mmap
import struct

import fitz
from PIL import Image
from magic import from_file

from mglib.exceptions import FileTypeNotSupported

"""
Uses command line pymupdf (fitz), PIL and the struct module for various
small operations (e.g. get pdf page count).
"""

logger = logging.getLogger(__name__)


def get_tiff_pagecount(filepath):
    # Get page count from the file. On any errors defer to PIL for page count.
    with open(filepath, 'rb') as input_file:
        try:
            fmap = mmap.mmap(input_file.fileno(), 0)
        except (WindowsError, OSError):
            fmap = None
        except ValueError:
            return get_pagecount_pil(filepath)

        page_count = 0

        # Set the byte order from the first 2 bytes of the file.
        try:
            if fmap:
                bom = struct.unpack('2s', fmap[0:2])[0]
            else:
                input_file.seek(0)
                bom = struct.unpack('2s', input_file.read(2))[0]
            if bom == b'II':
                byte_order = '<'  # Little Endian.
            elif bom == b'MM':
                byte_order = '>'  # Big Endian.
            else:
                logger.error('Unrecognised Byte Order: %s', bom)
                return get_pagecount_pil(filepath)

            # Check that the TIFF version is "42".
            if fmap:
                ver = int(struct.unpack('%sH' % byte_order, fmap[2:4])[0])
            else:
                input_file.seek(2)
                ver = int(struct.unpack('%sH' % byte_order, input_file.read(2))[0])
            if ver != 42:
                logger.error(f'Tiff version is {ver:d}. Should be 42.')
                return get_pagecount_pil(filepath)

            # Get first IDF.
            if fmap:
                offset = int(struct.unpack('%sL' % byte_order, fmap[4:8])[0])
            else:
                input_file.seek(4)
                offset = int(struct.unpack('%sL' % byte_order, input_file.read(4))[0])
            while offset:
                page_count += 1

                # Get number of tags in this IDF.
                if fmap:
                    tags = int(struct.unpack('%sH' % byte_order, fmap[offset:offset + 2])[0])
                else:
                    input_file.seek(offset)
                    tags = int(struct.unpack('%sH' % byte_order, input_file.read(2))[0])

                offset += (12 * tags)
                if fmap:
                    offset = int(struct.unpack('%sL' % byte_order, fmap[offset + 2:offset + 6])[0])
                else:
                    input_file.seek(offset + 2)
                    offset = int(struct.unpack('%sL' % byte_order, input_file.read(4))[0])
        except struct.error:
            return get_pagecount_pil(filepath)
    return page_count


def get_pagecount_pil(filepath):
    """
    Using PIL, load the image into a Multipage object and return the page count.
    """
    im = Image.open(filepath)

    try:
        page_count = im.n_frames or 1
    except AttributeError:
        page_count = 1
    return page_count


def get_pagecount(filepath):
    """
    Returns the number of pages in a PDF document as integer.

    filepath - is filesystem path to a PDF document
    """
    if not os.path.isfile(filepath):
        raise ValueError(f'Filepath {filepath} is not a file')

    if os.path.isdir(filepath):
        raise ValueError(f'Filepath {filepath} is a directory!')

    base, ext = os.path.splitext(filepath)
    mime_type = from_file(filepath, mime=True)
    # pure images (png, jpeg) have only one page :)

    if mime_type in ('image/png', 'image/jpeg', 'image/jpg'):
        # whatever png/jpg image is there - it is
        # considered by default one-page document.
        return 1

    # In case of REST API upload (via PUT + form multipart)
    # django saves temporary file as application/octet-stream
    # Checking extensions is an extra method of finding out correct
    # mime type
    if ext and ext.lower() in ('.jpeg', '.png', '.jpg'):
        return 1

    if mime_type == 'image/tiff':
        return get_tiff_pagecount(filepath)

    # In case of REST API upload (via PUT + form multipart)
    # django saves temporary file as application/octet-stream
    # Checking extensions is an extra method of finding out correct
    # mime type
    if ext and ext.lower() in ('.tiff', '.tif'):
        return get_tiff_pagecount(filepath)

    if mime_type != 'application/pdf':
        # In case of REST API upload (via PUT + form multipart)
        # django saves temporary file as application/octet-stream
        # Checking extensions is an extra method of finding out correct
        # mime type
        if ext and ext.lower() != '.pdf':
            raise FileTypeNotSupported(
                "Only jpeg, png, pdf and tiff are handled by this"
                " method"
            )

    # If we're still here, we're dealing with a PDF file.

    with fitz.Document(filepath) as doc:
        page_count = len(doc)

    if not page_count:
        raise Exception('Error occurred while getting document page count.')

    return page_count
