import pytest
from hypothesis import given, settings
from hypothesis import HealthCheck
from hypothesis.strategies import text, lists, dictionaries
from protocol import MRImagingProtocol, \
    DicomImagingSequence  # Replace with actual import path
from protocol.utils import convert2ascii


# Test initialization and defaults
def test_initialization_defaults():
    protocol = MRImagingProtocol()
    assert protocol.name == 'MRIProtocol'
    assert protocol.category == 'MR'
    assert len(protocol._seq) == 0


# Test adding sequences
def test_add_sequence(sample_dcm):
    sequence = DicomImagingSequence(dicom=sample_dcm)
    protocol = MRImagingProtocol()
    protocol.add(sequence)
    assert len(protocol._seq) == 1
    assert protocol[sequence.name] == sequence


def test_add_invalid_type():
    with pytest.raises(TypeError):
        _ = MRImagingProtocol(name="TestProtocol",
                              category="TestCategory")


def test_add_duplicate_name(sample_dcm):
    protocol = MRImagingProtocol()
    sequence1 = DicomImagingSequence(name="Sequence1", dicom=sample_dcm)
    sequence2 = DicomImagingSequence(name="Sequence1", dicom=sample_dcm)
    protocol.add(sequence1)
    with pytest.raises(ValueError):
        protocol.add(sequence2)


# Test protocol emptiness
def test_protocol_emptiness():
    empty_protocol = MRImagingProtocol()
    assert not empty_protocol
    non_empty_protocol = MRImagingProtocol()
    non_empty_protocol.add(DicomImagingSequence())
    assert non_empty_protocol


# Test getting sequences
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture],
          deadline=None)
@given(sequence_name=text())
def test_get_sequence(sequence_name, sample_dcm):
    protocol = MRImagingProtocol()
    seq_name = convert2ascii(sequence_name)
    if not seq_name:
        with pytest.raises(ValueError):
            _ = DicomImagingSequence(name=sequence_name,
                                            dicom=sample_dcm)
    else:
        sequence = DicomImagingSequence(name=sequence_name, dicom=sample_dcm)
        protocol.add(sequence)
        assert len(protocol._seq) == 1


def test_get_non_existing_sequence():
    protocol = MRImagingProtocol()
    with pytest.raises(KeyError):
        retrieved_sequence = protocol["NonExistingSequence"]


# Run the tests
if __name__ == "__main__":
    pytest.main([__file__])
