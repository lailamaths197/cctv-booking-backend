import io
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import serializers

MAX_DIMENSION = 1600
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def process_image(upload):
    """Validate, normalise and re-encode one uploaded photo.

    * rejects anything that is not a real JPEG/PNG/WEBP (checked with Pillow,
      not just the file extension or Content-Type header)
    * enforces the size limit from settings.MAX_UPLOAD_SIZE_MB
    * applies EXIF rotation, downsizes to MAX_DIMENSION and strips metadata
      (including GPS data) by re-encoding as JPEG
    * returns a ContentFile with a random filename so user-supplied names are
      never used on disk
    """
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if upload.size > max_bytes:
        raise serializers.ValidationError(
            f"Image is too large. Maximum size is {settings.MAX_UPLOAD_SIZE_MB} MB each."
        )

    try:
        upload.seek(0)
        probe = Image.open(upload)
        probe.verify()  # integrity check; invalidates the image object
        upload.seek(0)
        image = Image.open(upload)
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise serializers.ValidationError("Upload valid images only (JPEG, PNG or WEBP).")

    if image.format not in ALLOWED_FORMATS:
        raise serializers.ValidationError("Unsupported image type. Use JPEG, PNG or WEBP.")

    image = ImageOps.exif_transpose(image)
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    if image.mode != "RGB":
        image = image.convert("RGB")

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.jpg")


def process_images(uploads):
    """Process an array of uploads (the `images` multipart key, repeated)."""
    limit = settings.MAX_IMAGES_PER_UPLOAD
    if len(uploads) > limit:
        raise serializers.ValidationError(f"You can upload at most {limit} images at a time.")
    return [process_image(u) for u in uploads]
