# test parser of ReceiveCoilActiveElements
import unittest
from pathlib import Path

from protocol import SiemensMRImagingProtocol
from protocol.imaging import ReceiveCoilActiveElements, ImagingSequence
from protocol.tests.conftest import THIS_DIR
from protocol.tests.utils import download


def is_compliant(value, ref_value, param_name, body_part_examined=None):
    """Check if two values are equal"""
    param_cls = ImagingSequence.import_string(f'protocol.imaging.{param_name}')
    param = param_cls(value)
    ref_param = param_cls(ref_value)
    return ref_param.compliant(param, body_part_examined=body_part_examined)


class TestReceiveCoilActiveElements(unittest.TestCase):
    param_name = 'ReceiveCoilActiveElements'

    def test_compare_coil_names(self):
        """Test if coil names are compared correctly"""
        value = 'HEA;HEP'
        reference = 'HEP;HEA'
        self.assertTrue(is_compliant(value, reference, self.param_name))

        value = 'BO1,2;BO1-3;SP2-5'
        reference = 'BO1,2;BO3;SP4,5'
        self.assertTrue(is_compliant(value, reference, self.param_name))

        value = 'BO1,2;BO1-3;SP2-5'
        reference = 'BO1,2;BO1-3;SP2-5'
        self.assertTrue(is_compliant(value, reference, self.param_name))

    def test_compare_coil_names_with_body_part_examined(self):
        body_part_examined = 'BRAIN'
        value = 'HC1-7;SP2-5'
        reference = 'HC1-7;NC1,2'
        self.assertFalse(is_compliant(value, reference,
                                      self.param_name, body_part_examined))
        value = 'HC1-7'
        reference = 'HC1-7;NC1,2'
        self.assertTrue(is_compliant(value, reference,
                                     self.param_name, body_part_examined))
        value = 'HC1-7;NC1,2'
        reference = 'HC1-7'
        self.assertTrue(is_compliant(value, reference,
                                     self.param_name, body_part_examined))
        value = 'HC1,3-7'
        reference = 'HC1-7;NC1,2'
        self.assertTrue(is_compliant(value, reference,
                                     self.param_name, body_part_examined))
        value = 'HC1,3'
        reference = 'HC1-3;NC1,2'
        self.assertTrue(is_compliant(value, reference,
                                     self.param_name, body_part_examined))
        value = 'HC1-3'
        reference = 'HC1,3'
        self.assertTrue(is_compliant(value, reference,
                                     self.param_name, body_part_examined))

    def test_compliant_direction(self):
        body_part_examined = 'BRAIN'

        value = 'HC1-7'
        reference = 'HC1-7;SP2-5'
        self.assertFalse(is_compliant(value, reference,
                                      self.param_name, body_part_examined))

        value = 'HC1-7;SP2-5'
        reference = 'HC1-7'
        self.assertFalse(is_compliant(value, reference,
                                      self.param_name, body_part_examined))


def test_parse_receive_coil_active_elements():
    value = 'HEA;HEP'
    rcae = ReceiveCoilActiveElements(value)
    assert str(rcae) == 'RCAE(HEA;HEP)'
    assert rcae.get_value() == {'HEA': [], 'HEP': []}

    possible_coil_names = ['15K',
                           'BC',
                           'BO1,2;BO1-3;SP2-5',
                           'BO1,2;BO3;SP4,5',
                           'BO1,2;SP2,3',
                           'BO1-3;BO1-3;SP2-6',
                           'BO1-3;BO1-3;SP3-5',
                           'BO1-3;BO1-3;SP3-6',
                           'BO1-3;BO1;SP4-6',
                           'BO1-3;SP2,3',
                           'BO1-3;SP2-4',
                           'BO1-3;SP3,4',
                           'BO2,3;SP2-4',
                           'BO3;BO1-3;SP5-7',
                           'BP1,2;BP1,2;BP1,2;SP4-6',
                           'BP1,2;BP1,2;BP1,2;SP5-7',
                           'BP1,2;BP1,2;BP1;SP3-5',
                           'BP1,2;BP1,2;BP1;SP5,6',
                           'BP1,2;BP1,2;SP1-3',
                           'BP1,2;BP1,2;SP3-5',
                           'BP1,2;BP1,2;SP4,5',
                           'BP1,2;BP1,2;SP4-6',
                           'BP1,2;BP1,2;SP5-7',
                           'BP1,2;BP1,2;SP6,7',
                           'BP1,2;BP1;BP1,2;SP5-7',
                           'BP1,2;BP1;SP2-4',
                           'BP1,2;BP1;SP3-5',
                           'BP1,2;BP1;SP4-6',
                           'BP1,2;BP2;BP1,2;SP5-7',
                           'BP1,2;BP2;BP1;SP4-6',
                           'BP1,2;BP2;BP1;SP5-7',
                           'BP1,2;SP1-3',
                           'BP1,2;SP2,3',
                           'BP1,2;SP2-4',
                           'BP1,2;SP4-6',
                           'BP1,2;SP5,6',
                           'BP1,2;SP5-7',
                           'BP1,2;SP6,7',
                           'BP1,2;SP6-8',
                           'BP1,2;SP7,8',
                           'BP2;BP1;SP2-4',
                           'BP2;BP1;SP3,4',
                           'BP2;BP1;SP3-5',
                           'C:1H',
                           'C:AC',
                           'C:BC',
                           'C:HEA;HEP',
                           'C:HEP',
                           'C:KN',
                           'C:R01-32',
                           'C:R09-32;PH1-8',
                           'FL',
                           'FS',
                           'FS;SP1',
                           'FS;SP1,2',
                           'FS;SP1-3',
                           'FS;SP2,3',
                           'FS;SP2-4',
                           'FS;SP3,4',
                           'FS;SP3-5',
                           'FS;SP4',
                           'FS;SP4,5',
                           'FS;SP5,6',
                           'HC1,3-7',
                           'HC1-4',
                           'HC1-6',
                           'HC1-6;NC1,2',
                           'HC1-7',
                           'HC1-7;NC1',
                           'HC1-7;NC1,2',
                           'HC1-7;NC2',
                           'HC2,4,6,7',
                           'HC2,4,6,7;NC2',
                           'HC2-7;NC1,2',
                           'HC3-6',
                           'HC3-7',
                           'HC3-7;NC1',
                           'HC3-7;NC1,2',
                           'HC5-7',
                           'HC5-7;NC1',
                           'HC7;NC1,2',
                           'HC7;NC1,2;SP2-5',
                           'HE1-4',
                           'HE1-4;NE1,2',
                           'HE1-4;NE2',
                           'HEA;HEP',
                           'HEA;HEP;NEA;NEP',
                           'HEP',
                           'HHA;HHP',
                           'L11',
                           'NEA;NEP;SP1',
                           'NEP;SP1',
                           'SHL',
                           'SHS',
                           'SP2-4',
                           'SP2-5',
                           'SP3,4',
                           'SP3-5',
                           'SP3-6',
                           'SP4-6',
                           'SP5-7',
                           'T:HEA;HEP',
                           'T:HEP']
    for coil in possible_coil_names:
        rcae = ReceiveCoilActiveElements(coil)
        print(str(rcae))
        print(rcae.get_value())


def test_mr_protocol_xml_parsing():
    # Using an example XML file from the following Github repository
    # https://github.com/lrq3000/mri_protocol
    url = 'https://raw.githubusercontent.com/lrq3000/mri_protocol/master/SiemensVidaProtocol/Coma%20Science%20Group.xml'  # noqa
    filename = THIS_DIR / 'coma_science.xml'
    xml_file = Path(filename)

    if not xml_file.is_file():
        download(url, filename)

    protocol = SiemensMRImagingProtocol(filepath=xml_file)
    print(protocol)
