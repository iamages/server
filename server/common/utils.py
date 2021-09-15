from distutils.util import strtobool

from fastapi import HTTPException, status


def handle_str2bool(boolstr):
    if isinstance(boolstr, bool):
        return boolstr
    try:
        return bool(strtobool(boolstr))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)
