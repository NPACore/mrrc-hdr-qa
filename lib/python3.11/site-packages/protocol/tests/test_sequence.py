# Write tests for the imaging module

import pytest
import pydicom
from pathlib import Path
from protocol import DicomImagingSequence, logger
from protocol.config import Unspecified, UnspecifiedType
from protocol.imaging import MultiValueEchoTime, MultiValueEchoNumber
from protocol.utils import get_dicom_param_value, header_exists, \
    parse_csa_params

import pytest
from hypothesis import given
from hypothesis.strategies import dictionaries, text, floats, lists

# Import your class here
from protocol import DicomImagingSequence

# Hypothesis strategy for valid DICOM parameters
dicom_params = dictionaries(
    keys=text(min_size=1),
    values=floats(allow_nan=False, allow_infinity=False)
)

# # Test multi-echo handling
# def test_multi_echo_handling():
#     seq = DicomImagingSequence()
#     seq.set_echo_times([20.0, 30.0], echo_number=2)
#     assert seq.multi_echo
#     assert seq['EchoTime'].values == [20.0, 30.0]
#     assert seq['EchoNumber'].value == 2

# Add more tests based on the outlined property tests

# Run tests
if __name__ == '__main__':
    pytest.main()
