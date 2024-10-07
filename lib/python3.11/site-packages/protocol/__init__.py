# -*- coding: utf-8 -*-

"""Top-level package for protocol."""

__author__ = """Pradeep Reddy Raamana"""
__email__ = 'raamana@gmail.com'
# __version__ = '0.1.0'

import logging
import sys

from protocol.config import configure_logger

logger = logging.getLogger(__name__)
logger = configure_logger(logger, mode='w', output_dir=None)


from protocol.base import (BaseParameter, BaseSequence, BaseProtocol)
from protocol.config import (BASE_IMAGING_PARAMETER_NAMES,
                             BASE_IMAGING_PARAMS_DICOM_TAGS,
                             ACRONYMS_IMAGING_PARAMETERS,
                             UnspecifiedType)
from protocol.imaging import (DicomImagingSequence, BidsImagingSequence,
                              SiemensMRImagingProtocol, MRImagingProtocol)

try:
    from protocol._version import __version__
except ImportError:
    if sys.version_info < (3, 8):
        from importlib_metadata import version
    else:
        from importlib.metadata import version

    try:
        __version__ = version('protocol')
    except Exception:
        __version__ = "unknown"
