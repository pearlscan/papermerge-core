import logging
import magic

logger = logging.getLogger(__name__)


class Mime:
    def __init__(self, filepath):
        self.filepath = filepath

        try:
            self.mime_type = magic.from_file(self.filepath, mime=True)
        except FileNotFoundError:
            self.mime_type = None

    def is_tiff(self):
        return self.mime_type == 'image/tiff'

    def is_pdf(self):
        return self.mime_type == 'application/pdf'

    def is_image(self):
        """
        Returns true if MIME type is one of following:
            * image/png
            * image/jpg
        """
        return self.mime_type in ('image/png', 'image/jpg', 'image/jpeg')

    def is_dicom(self):
        return self.mime_type == 'application/dicom'

    def __str__(self):
        return f'Mime({self.filepath}, {self.mime_type})'
