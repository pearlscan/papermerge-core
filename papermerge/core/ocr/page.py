import os
import logging
import time

from django.conf import settings
from django.template.loader import get_template

from papermerge.core.lib.dicom import convert_dicom2pdf, dicom_to_dict
from papermerge.core.models import Document
from papermerge.core.storage import default_storage
from papermerge.core import signal_definitions as signals

from papermerge.core.lib import mime
from papermerge.core.lib.pdfinfo import get_pagecount
from mglib.path import (
    DocumentPath,
    PagePath,
)
from mglib.step import (Step, Steps)
from mglib.shortcuts import (
    extract_img,
    resize_img,
    extract_hocr,
    extract_txt,
)
from PIL import Image
from papermerge.core.lib.tiff import convert_tiff2pdf
from papermerge.core.views.utils import sanitize_kvstore_list

logger = logging.getLogger(__name__)

STARTED = "started"
COMPLETE = "complete"


def notify_hocr_ready(page_path, **kwargs):
    """
    Notifies interested parties that .hocr file is available.

    Notifies via django signals. Among others will send
    hocr content itself. Input arguments:

    ``page_path``: mglib.PagePath instance of current page
    Following keys are expected to be availble in kwargs dictinary:

        * ``user_id``
        * ``document_id``
        * ``file_name``
        * ``page_num``
        * ``namespace``
        * ``version``
        * ``step``

    Always returns None.

    Sent signals: ``post_page_hocr``.

    Following arguments are passed to the signal:
        * ``sender`` = from papermerge.core.signal_definitions.WORKER
        * ``user_id``
        * ``document_id``
        * ``file_name``
        * ``page_num``
        * ``lang``
        * ``version``
        * ``namespace`` = may be empty. Used to distinguish among
            different tenants in multi-tenant deployments.
        * ``step`` = integer number corresponding to step
            learn more about steps in ``mglib.step.Step``
        * ``hocr`` = extracted hocr data (text format)
    """

    user_id = kwargs.get('user_id', None)
    document_id = kwargs.get('document_id', None)
    file_name = kwargs.get('file_name', None)
    page_num = kwargs.get('page_num', 1)
    version = kwargs.get('version', 0)
    namespace = kwargs.get('namespace', None)
    step = kwargs.get('step', 1)

    if page_path:
        abs_path_hocr = default_storage.abspath(page_path.hocr_url())

        if os.path.exists(abs_path_hocr):
            with open(abs_path_hocr) as f:
                hocr = f.read()

                signals.post_page_hocr.send(
                    sender=signals.WORKER,
                    user_id=user_id,
                    document_id=document_id,
                    file_name=file_name,
                    page_num=page_num,
                    step=step,
                    namespace=namespace,
                    version=version,
                    hocr=hocr
                )
        else:
            logger.warning(
                f"Page hocr/step={step} path {abs_path_hocr} does not exist."
            )
    else:
        logger.warning(
            f"hOCR/step={step} method returned empty page path."
        )


def notify_txt_ready(page_path, **kwargs):
    """
    Notifies interested parties that .txt file is available.

    Notifies via django signals. Among others will send
    .txt content itself. Input arguments:

    ``page_path``: mglib.PagePath instance of current page
    Following keys are expected to be availble in kwargs dictinary:

        * ``user_id``
        * ``document_id``
        * ``file_name``
        * ``page_num``
        * ``version``
        * ``namespace``

    Always returns None.

    Sent signals: ``post_page_txt``.

    Following arguments are passed to the signal:
        * ``sender`` = from papermerge.core.signal_definitions.WORKER
        * ``user_id``
        * ``document_id``
        * ``file_name``
        * ``page_num``
        * ``version``
        * ``lang``
        * ``namespace`` = may be empty. Used to distinguish among
            different tenants in multi-tenant deployments.
        * ``txt`` = extracted .txt data (text format)
    """

    user_id = kwargs.get('user_id', None)
    document_id = kwargs.get('document_id', None)
    page_num = kwargs.get('page_num', 1)
    file_name = kwargs.get('file_name', None)
    version = kwargs.get('version', 0)
    namespace = kwargs.get('namespace', None)

    logger.debug("notify_txt_ready")

    if page_path:
        abs_path_txt = default_storage.abspath(page_path.txt_url())

        logger.debug(f"notify_txt_ready for {abs_path_txt}")

        if os.path.exists(abs_path_txt):
            with open(abs_path_txt) as f:
                text = f.read()

                logger.debug(
                    f"Sending post_page_txt signal"
                    f" namespace={namespace} "
                    f" user_id={user_id}"
                    f" document_id={document_id}"
                    f" page_num={page_num}"
                    f" text=[{len(text):,} chars] {' '.join(text[:20].splitlines())}..."
                )
                signals.post_page_txt.send(
                    sender=signals.WORKER,
                    user_id=user_id,
                    document_id=document_id,
                    file_name=file_name,
                    page_num=page_num,
                    version=version,
                    namespace=namespace,
                    text=text
                )
        else:
            logger.warning(
                f"Page txt path {abs_path_txt} does not exist. "
                f"Page indexing was skipped."
            )
    else:
        logger.warning(
            "OCR method returned empty page path. "
            "Page indexing was skipped."
        )


def notify_pre_page_ocr(page_path, **kwargs):
    user_id = kwargs.get('user_id', None)
    document_id = kwargs.get('document_id', None)
    file_name = kwargs.get('file_name', None)
    page_num = kwargs.get('page_num', 1)
    version = kwargs.get('version', 0)
    namespace = kwargs.get('namespace', None)

    signals.pre_page_ocr.send(
        sender=signals.WORKER,
        user_id=user_id,
        document_id=document_id,
        file_name=file_name,
        page_num=page_num,
        version=version,
        namespace=namespace,
    )


def ocr_page_pdf(
    doc_path: DocumentPath,
    page_num: int,
    lang: str,
    **kwargs
) -> PagePath:
    """
    doc_path is an mglib.path.DocumentPath instance

    On success returns ``mglib.path.PagePath`` instance.
    """
    logger.debug("OCR PDF document")

    file_name = kwargs.pop('file_name', None)

    if not file_name:
        file_name = doc_path.file_name

    page_count = get_pagecount(
        default_storage.abspath(doc_path.url())
    )

    if page_num > page_count:
        raise ValueError(
            f"Page number {page_num} is greater than page count {page_count}"
        )

    # first quickly generate preview images
    page_path = PagePath(
        document_path=doc_path,
        page_num=page_num,
        step=Step(1),
        page_count=page_count
    )
    for step in Steps():
        page_path.step = step
        extract_img(
            page_path,
            media_root=settings.MEDIA_ROOT
        )

    notify_pre_page_ocr(
        page_path,
        page_num=page_num,
        lang=lang,
        file_name=doc_path.file_name,
        **kwargs
    )

    page_path = PagePath(
        document_path=doc_path,
        page_num=page_num,
        step=Step(1),
        page_count=page_count
    )
    extract_txt(
        page_path,
        lang=lang,
        media_root=settings.MEDIA_ROOT
    )
    notify_txt_ready(
        page_path,
        page_num=page_num,
        lang=lang,
        file_name=file_name,
        **kwargs
    )

    for step in Steps():
        page_path.step = step
        if not step.is_thumbnail:
            extract_hocr(
                page_path,
                lang=lang,
                media_root=settings.MEDIA_ROOT
            )
            notify_hocr_ready(
                page_path,
                page_num=page_num,
                lang=lang,
                # step as integer number
                step=step.current,
                file_name=file_name,
                **kwargs
            )

    return page_path


def ocr_page_dicom(
        doc_path: DocumentPath,
        page_num: int,
        lang: str,
        dicom_dict: dict,
        **kwargs
) -> PagePath:
    """
    We're not really OCRing a DICOM file, but we're extracting the data and
    supplying it as OCR text to workaround metadata not being searchable.
    """
    logger.debug("OCR DICOM document")

    file_name = kwargs.pop('file_name', None)

    if not file_name:
        file_name = doc_path.file_name

    # Always single page when processing DICOM, so we may as well just set it
    # manually.
    page_count = 1

    if page_num > page_count:
        raise ValueError(
            f"Page number {page_num} is greater than page count {page_count}"
        )

    # first quickly generate preview images
    page_path = PagePath(
        document_path=doc_path,
        page_num=page_num,
        step=Step(1),
        page_count=page_count
    )
    for step in Steps():
        page_path.step = step
        extract_img(
            page_path,
            media_root=settings.MEDIA_ROOT
        )

    notify_pre_page_ocr(
        page_path,
        page_num=page_num,
        lang=lang,
        file_name=doc_path.file_name,
        **kwargs
    )

    page_path = PagePath(
        document_path=doc_path,
        page_num=page_num,
        step=Step(1),
        page_count=page_count
    )
    txt_path = os.path.join(
        settings.MEDIA_ROOT, page_path.txt_url()
    )
    with open(txt_path, 'w', encoding='utf-8') as txt_file:
        txt_file.write(str(dicom_dict))
    notify_txt_ready(
        page_path,
        page_num=page_num,
        lang=lang,
        file_name=file_name,
        **kwargs
    )

    for step in Steps():
        page_path.step = step
        if not step.is_thumbnail:
            # There's no point OCRing the DICOM file, so we'll just create a
            # hocr file with the minimum amount of XML to still be valid so that
            # we don't need to change too much code.

            img_path = os.path.join(
                settings.MEDIA_ROOT, page_path.img_url()
            )
            hocr_path = os.path.join(
                settings.MEDIA_ROOT, page_path.hocr_url()
            )

            with Image.open(img_path) as img:
                width, height = img.size

            hocr_template = get_template('core/blank_result.hocr')
            hocr_body = hocr_template.render({
                'img_path': img_path,
                'width': width,
                'height': height
            })

            with open(hocr_path, 'w', encoding='utf-8') as hocr_file:
                hocr_file.write(hocr_body)

            notify_hocr_ready(
                page_path,
                page_num=page_num,
                lang=lang,
                # step as integer number
                step=step.current,
                file_name=file_name,
                **kwargs
            )

    return page_path


def ocr_page_image(
    doc_path,
    page_num,
    lang,
    **kwargs
):
    """
    image = jpg, jpeg, png

    On success returns ``mglib.path.PagePath`` instance.
    """
    logger.debug("OCR image (jpeg, jpg, png) document")

    page_path = PagePath(
        document_path=doc_path,
        page_num=page_num,
        step=Step(1),
        # jpeg, jpg, png are 1 page documents
        page_count=1
    )
    notify_pre_page_ocr(
        page_path,
        page_num=page_num,
        lang=lang,
        file_name=doc_path.file_name,
        **kwargs
    )
    # resize and eventually convert (png -> jpg)
    resize_img(
        page_path,
        media_root=settings.MEDIA_ROOT
    )
    extract_txt(
        page_path,
        lang=lang,
        media_root=settings.MEDIA_ROOT
    )
    notify_txt_ready(
        page_path,
        page_num=page_num,
        lang=lang,
        file_name=doc_path.file_name,
        **kwargs
    )

    # First quickly generate preview images
    for step in Steps():
        page_path.step = step
        resize_img(
            page_path,
            media_root=settings.MEDIA_ROOT
        )
    # reset page's step
    page_path.step = Step(1)
    # Now OCR each image
    for step in Steps():
        if not step.is_thumbnail:
            extract_hocr(
                page_path,
                lang=lang,
                media_root=settings.MEDIA_ROOT
            )
            notify_hocr_ready(
                page_path,
                page_num=page_num,
                lang=lang,
                # step as integer number
                step=step.current,
                file_name=doc_path.file_name,
                **kwargs
            )

    return page_path


def ocr_page(
    user_id,
    document_id,
    file_name,
    page_num,
    lang,
    version,
    namespace=None,
):
    logger.debug(
        f" ocr_page user_id={user_id} doc_id={document_id}"
        f" page_num={page_num}"
    )
    t1 = time.time()
    lang = lang.lower()
    doc_path = DocumentPath(
        user_id=user_id,
        document_id=document_id,
        file_name=file_name,
        version=version
    )

    if not default_storage.exists(doc_path.url()):
        # In case of distibuted deployment, document uploaded
        # by webapp is not directly available to the worker (which runs on
        # separate computer). Thus, if document is not locally available,
        # worker will download the document from whatever remote location.
        default_storage.download(
            doc_path_url=doc_path.url(),
            namespace=namespace
        )

    mime_type = mime.Mime(
        default_storage.abspath(doc_path.url())
    )
    logger.debug(f"Mime Type = {mime_type}")

    page_type = ''

    if mime_type.is_pdf():
        ocr_page_pdf(
            doc_path=doc_path,
            page_num=page_num,
            lang=lang,
            user_id=user_id,
            version=version,
            document_id=document_id,
            namespace=namespace
        )
        page_type = 'pdf'
    elif mime_type.is_image():  # jpeg, jpeg or png
        ocr_page_image(
            doc_path=doc_path,
            page_num=page_num,
            lang=lang,
            user_id=user_id,
            document_id=document_id,
            namespace=namespace,
            version=version
        )
    elif mime_type.is_tiff():
        # new filename is a pdf file
        logger.debug("TIFF type detected")
        new_filename = convert_tiff2pdf(
            doc_url=default_storage.abspath(doc_path.url())
        )
        # now .pdf
        orig_file_name = doc_path.file_name
        doc_path.file_name = new_filename
        # and continue as usual
        ocr_page_pdf(
            doc_path=doc_path,
            page_num=page_num,
            lang=lang,
            user_id=user_id,
            document_id=document_id,
            # Pass original file_name i.e. tiff file name as well.
            file_name=orig_file_name,
            namespace=namespace,
            version=version
        )
    elif mime_type.is_dicom():
        # new filename is a pdf file
        logger.debug('DICOM type detected')

        # Extract dicom metadata before we change the path to PDF.
        dicom_dict = dicom_to_dict(
            default_storage.abspath(doc_path.url())
        )

        new_filename = convert_dicom2pdf(
            doc_url=default_storage.abspath(doc_path.url())
        )
        # now .pdf
        orig_file_name = doc_path.file_name
        doc_path.file_name = new_filename
        # and continue as usual
        ocr_page_dicom(
            doc_path=doc_path,
            page_num=page_num,
            lang=lang,
            dicom_dict=dicom_dict,
            user_id=user_id,
            document_id=document_id,
            # Pass original file_name i.e. tiff file name as well.
            file_name=orig_file_name,
            namespace=namespace,
            version=version
        )
        if dicom_dict:
            doc = Document.objects.get(id=document_id)
            page = doc.pages.first()

            kvstore = [
                {'key': k, 'value': v, 'kv_type': 'text', 'kv_inherited': False}
                for k, v in dicom_dict.items()
            ]
            page.kv.update(
                sanitize_kvstore_list(kvstore)
            )
    else:
        logger.error(
            f" user_id={user_id}"
            f" doc_id={document_id}"
            f" page_num={page_num} error=Unknown file type"
        )
        return True

    t2 = time.time()
    logger.debug(
        f" user_id={user_id} doc_id={document_id}"
        f" page_num={page_num} page_type={page_type}"
        f" total_exec_time={t2-t1:.2f}"
    )

    return True
