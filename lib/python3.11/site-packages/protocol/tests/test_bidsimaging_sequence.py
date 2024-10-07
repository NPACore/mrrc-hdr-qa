from pathlib import Path

from protocol import BidsImagingSequence

THIS_DIR = Path(__file__).parent


def test_parameters():
    sequence = BidsImagingSequence(bidsfile=THIS_DIR / 'resources/sample.json',
                                   path=THIS_DIR / 'resources')
    str_repr = str(sequence)
    assert 'Invalid' not in str_repr
    assert 'Unspecified' not in str_repr


