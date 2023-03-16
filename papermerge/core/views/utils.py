from django.utils.html import escape


def sanitize_kvstore(kvstore_dict):
    """
    Creates a sanitized dictionary.

    Sanitized dictionary contains only allowed keys and escaped values.
    """
    allowed_keys = {
        'id',
        'key',
        'value',
        'kv_type',
        'kv_format',
        'kv_inherited',
    }

    sanitized_kvstore_dict = {
        k: v if isinstance(v, bool) else escape(v)
        for k, v in kvstore_dict.items()
        if k in allowed_keys
    }

    return sanitized_kvstore_dict


def sanitize_kvstore_list(kvstore_list):
    """
    Creates a new list of sanitized dictionaries.

    Sanitizied dictionary contains only allowed keys and escaped values.
    """
    if not isinstance(kvstore_list, list):
        raise ValueError("Expects list type as input")

    new_kvstore_list = [
        sanitize_kvstore(item) for item in kvstore_list
    ]

    return new_kvstore_list
