import re
from abc import ABC
from bisect import insort
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from importlib import import_module
from pathlib import Path

import numpy as np
import pydicom
from lxml import objectify
from protocol import config as cfg, logger
from protocol.base import (BaseImagingProtocol, BaseParameter, BaseSequence,
                           CategoricalParameter, MultiValueCategoricalParameter,
                           MultiValueNumericParameter, NumericParameter)
from protocol.config import (ACRONYMS_IMAGING_PARAMETERS as ACRONYMS_IMG,
                             BASE_IMAGING_PARAMS_DICOM_TAGS as DICOM_TAGS,
                             SESSION_INFO_DICOM_TAGS as SESSION_TAGS,
                             ACRONYMS_DEMOGRAPHICS as ACRONYMS_DEMO,
                             PARAMETERS_ANALOGUES_DICT as ANALOGUES_DICT,
                             Invalid, Unspecified, UnspecifiedType,
                             ProtocolType, valid_neck_coils, INVALID_PARAMETERS)
from protocol.utils import (auto_convert, convert2ascii, get_dicom_param_value,
                            get_sequence_name, header_exists,
                            parse_csa_params, expand_number_range,
                            get_bids_param_value, read_json)


class Manufacturer(CategoricalParameter):
    """
    Parameter specific class for Manufacturer
    """

    _name = 'Manufacturer'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ManufacturersModelName(CategoricalParameter):
    """Parameter specific class for ManufacturersModelName"""

    _name = 'ManufacturersModelName'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SoftwareVersions(CategoricalParameter):
    """Parameter specific class for SoftwareVersions"""

    _name = 'SoftwareVersions'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class MagneticFieldStrength(NumericParameter):
    """Parameter specific class for MagneticFieldStrength"""

    _name = 'MagneticFieldStrength'

    def __init__(self, value=Unspecified):
        """Constructor."""
        if isinstance(value, str):
            if value.endswith('T'):
                value = value[:-1]
            try:
                value = float(value)
            except ValueError:
                raise ValueError(f"Could not convert {value} to float")

        super().__init__(name=self._name,
                         value=value,
                         units='T',
                         range=(0, 100),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ReceiveCoilName(CategoricalParameter):
    """Parameter specific class for ReceiveCoilName"""

    _name = 'ReceiveCoilName'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ReceiveCoilActiveElements(CategoricalParameter):
    """Parameter specific class for ReceiveCoilName"""

    _name = 'ReceiveCoilActiveElements'

    def __init__(self, value=Unspecified):
        """Constructor."""
        if not isinstance(value, UnspecifiedType):
            value = self.parse(value)
        else:
            self.__dict__['__str__'] = str(value)

        super().__init__(name=self._name,
                         value=value,
                         dtype=dict,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])

    def parse(self, value):
        coil_dict = {}
        # strings are of the form  'T:BP1,2;BP2,4,6;BP1,2;SP4-6',
        if ':' in value:
            # don't know what the header tag means but there are different
            #   values. For example, T, C
            header, coil_info = value.split(':')
            coil_dict['header'] = header
        else:
            coil_info = value

        parsed_values = defaultdict(list)
        for coil in coil_info.split(';'):
            # Use regular expression to find the leading alphabets
            # because there is no fixed length to coil name. It can be HC1,7 or HEA or L11
            has_leading_alphabets = re.match(r'^[a-zA-Z]+', coil)
            has_trailing_numbers = re.search(r'(\d+(?:[-,]\d+)*)$', coil)
            # Check if a match is found
            if has_leading_alphabets:
                body_part = has_leading_alphabets.group(0)
                if has_trailing_numbers:
                    coil_numbers = has_trailing_numbers.group(1)
                    expanded_numbers = expand_number_range(coil_numbers)
                    for num in expanded_numbers:
                        if num in parsed_values[body_part]:
                            continue
                        else:
                            # add the number to the list in sorted order
                            # this is required to compare lists later
                            insort(parsed_values[body_part], num)
                else:
                    parsed_values[body_part] = []
            else:
                break

        self.__dict__['__str__'] = coil_info
        # cast defaultdict to dict
        coil_dict = dict(parsed_values)
        return coil_dict

    def __repr__(self):
        """repr"""
        name = self.acronym if self.acronym else self.name
        try:
            return f"{name}({self.__dict__['__str__']})"
        except KeyError:
            return f"{name}({self._value})"

    def get_value(self):
        return self._value

    def _check_compliance(self, other, **kwargs):
        """Method to check if one parameter value is compatible w.r.t another,
            either in equality or within acceptable range, for that data type.
        """
        # If body part examined is HEAD, BRAIN, then only compare the head coils
        # Non-compliance in neck coils or spine coils can be ignored.
        ignore_list = []
        if kwargs.get('body_part_examined', None):
            bpe = kwargs['body_part_examined']
            if not isinstance(bpe, UnspecifiedType):
                if bpe in ['HEAD', 'BRAIN']:
                    ignore_list.extend(valid_neck_coils)
                    # ignore_list.extend(valid_spine_coils)

        # noinspection PyArgumentList
        return (self._compare_value(other, ignore_list=ignore_list)
                and self._compare_units(other))

    def _compare_value(self, other, **kwargs):
        ref_dict = self.get_value()
        other_dict = other.get_value()
        # TODO: check if the both have the a coil
        #  corresponding to the same body part from BODY_PART_EXAMINED
        if str(self) == str(other):
            # if complete string matches, return True
            return True
        else:
            # check if the coil names match and the numbers match
            coil_names_union = set(ref_dict.keys()).union(set(other_dict.keys()))
            ignore_list = kwargs.get('ignore_list', [])
            compare_coils = coil_names_union.difference(ignore_list)

            for coil_name in compare_coils:
                if coil_name not in ref_dict:
                    return False
                if coil_name not in other_dict:
                    return False
                # if ref_dict[coil_name] != other_dict[coil_name]:
                #     return False
            return True


class MRTransmitCoilSequence(CategoricalParameter):
    """Parameter specific class for MRTransmitCoilSequence"""

    _name = 'MRTransmitCoilSequence'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SequenceVariant(MultiValueCategoricalParameter):
    """Parameter specific class for SequenceVariant"""

    _name = 'SequenceVariant'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ScanOptions(CategoricalParameter):
    """Parameter specific class for ScanOptions"""

    _name = 'ScanOptions'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SequenceName(CategoricalParameter):
    """Parameter specific class for SequenceName"""

    _name = 'SequenceName'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ImageType(MultiValueCategoricalParameter):
    """Parameter specific class for ImageType"""

    _name = 'ImageType'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class NonLinearGradientCorrection(CategoricalParameter):
    """Parameter specific class for NonLinearGradientCorrection"""

    _name = 'NonLinearGradientCorrection'

    def __init__(self, value=Unspecified):
        """Constructor."""
        nlgc = self.parse(value)
        super().__init__(name=self._name,
                         value=nlgc,
                         dtype=bool,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])

    def parse(self, value):
        if not isinstance(value, UnspecifiedType):
            if isinstance(value, list):
                for i in value:
                    if i in ['DIS2D', 'DIS3D']:
                        return True
                    elif i in ['ND']:
                        return False
            elif isinstance(value, bool):
                return value
            else:
                raise ValueError("Expected a boolean value or Iterable.")
        return value


class MRAcquisitionType(CategoricalParameter):
    """Parameter specific class for MRAcquisitionType"""

    _name = 'MRAcquisitionType'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class MTState(CategoricalParameter):
    """Parameter specific class for MTState"""

    _name = 'MTState'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SpoilingState(CategoricalParameter):
    """Parameter specific class for SpoilingState"""

    _name = 'SpoilingState'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='optional',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ParallelReductionFactorInPlane(NumericParameter):
    """Parameter specific class for ParallelReductionFactorInPlane"""

    _name = 'ParallelReductionFactorInPlane'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ParallelAcquisitionTechnique(NumericParameter):
    """Parameter specific class for ParallelAcquisitionTechnique"""

    _name = 'ParallelAcquisitionTechnique'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PartialFourier(NumericParameter):
    """Parameter specific class for PartialFourier"""

    _name = 'PartialFourier'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PartialFourierDirection(NumericParameter):
    """Parameter specific class for PartialFourierDirection"""

    _name = 'PartialFourierDirection'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class DwellTime(NumericParameter):
    """Parameter specific class for DwellTime"""

    _name = 'DwellTime'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='s',
                         range=(0, 100),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class MultibandAccelerationFactor(NumericParameter):
    """Parameter specific class for MultibandAccelerationFactor"""

    _name = 'MultibandAccelerationFactor'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class EchoTrainLength(NumericParameter):
    """Parameter specific class for EchoTrainLength"""

    _name = 'EchoTrainLength'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PixelBandwidth(NumericParameter):
    """Parameter specific class for PixelBandwidth"""

    _name = 'PixelBandwidth'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='Hz',
                         range=(0, 100000),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PhaseEncodingSteps(NumericParameter):
    """Parameter specific class for PhaseEncodingSteps"""

    _name = 'PhaseEncodingSteps'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ShimSetting(MultiValueNumericParameter):
    """Parameter specific class for ShimSetting"""

    _name = 'ShimSetting'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=None,
                         acronym=ACRONYMS_IMG[self._name],
                         ordered=True)


class ShimMode(CategoricalParameter):
    """Parameter specific class for ShimSetting"""

    _name = 'ShimMode'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='critical',
                         dicom_tag=None,
                         acronym=ACRONYMS_IMG[self._name])


class MultiSliceMode(CategoricalParameter):
    """Parameter specific class for MultiSliceMode"""

    _name = 'MultiSliceMode'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         required=True,
                         severity='critical',
                         dicom_tag=None,
                         acronym=ACRONYMS_IMG[self._name])


class EchoNumber(NumericParameter):
    """Parameter specific class for EchoNumber"""

    _name = 'EchoNumber'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class RepetitionTime(NumericParameter):
    """Parameter specific class for RepetitionTime"""

    _name = 'RepetitionTime'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='ms',
                         range=(0, 100000),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class FlipAngle(NumericParameter):
    """Parameter specific class for FlipAngle"""

    _name = "FlipAngle"

    def __init__(self, value=Unspecified):
        """constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='degrees',
                         range=(0, 360),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])

        # overriding default from parent class
        self.decimals = 0

        # acceptable range could be achieved with different levels of tolerance
        #   from +/- 5 degrees to +/- 20 degrees
        self.abs_tolerance = 0  # degrees


class MultiValueEchoTime(MultiValueNumericParameter):
    """Parameter specific class for EchoTime"""

    _name = "EchoTime"

    def __init__(self, value=Unspecified):
        """constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='ms',
                         range=(0, 10000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class EchoTime(MultiValueNumericParameter):
    """Parameter specific class for EchoTime"""

    _name = "EchoTime"

    def __init__(self, value=Unspecified):
        """constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='ms',
                         range=(0, 10000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class MultiValueEchoNumber(MultiValueNumericParameter):
    """Parameter specific class for EchoTime"""

    _name = "EchoNumber"

    def __init__(self, value=Unspecified):
        """constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='ms',
                         range=(0, 10000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class EffectiveEchoSpacing(NumericParameter):
    """Parameter specific class for EffectiveEchoSpacing"""

    _name = "EffectiveEchoSpacing"

    def __init__(self, value=Unspecified):
        """constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='mm',
                         range=(0, 1000),
                         required=False,
                         severity='critical',
                         dicom_tag=None,
                         acronym=ACRONYMS_IMG[self._name])


class PhaseEncodingDirection(CategoricalParameter):
    """Parameter specific class for PhaseEncodingDirection"""

    _name = 'PhaseEncodingDirection'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name],
                         allowed_values=cfg.allowed_values_PED)


class InPlanePhaseEncodingDirection(CategoricalParameter):
    """Parameter specific class for InPlanePhaseEncodingDirection"""

    _name = 'InPlanePhaseEncodingDirection'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name],
                         allowed_values=['ROW', 'COL'])


class ScanningSequence(CategoricalParameter):
    """Parameter specific class for """

    _name = 'ScanningSequence'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PhasePolarity(CategoricalParameter):
    """Parameter specific class for """

    _name = 'PhasePolarity'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         dtype=int,
                         dicom_tag=None,
                         acronym=ACRONYMS_IMG[self._name])


class InversionTime(NumericParameter):
    """Parameter specific class for InversionTime"""

    _name = 'InversionTime'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='ms',
                         range=(0, 100000),
                         # TODO verify the accuracy of this range
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class BodyPartExamined(CategoricalParameter):
    """Parameter specific class for BodyPartExamined"""

    _name = 'BodyPartExamined'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PercentPhaseFOV(NumericParameter):
    """Parameter specific class for PercentPhaseFOV"""

    _name = 'PercentPhaseFOV'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='%',
                         range=(0, 100),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class NumberOfAverages(NumericParameter):
    _name = 'NumberOfAverages'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SliceThickness(NumericParameter):
    _name = 'SliceThickness'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='mm',
                         range=(0, 1000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PercentSampling(NumericParameter):
    _name = 'PercentSampling'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='%',
                         range=(0, 100),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class AngioFlag(CategoricalParameter):
    _name = 'AngioFlag'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ImagingFrequency(NumericParameter):
    _name = 'ImagingFrequency'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='Hz',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ImagedNucleus(CategoricalParameter):
    _name = 'ImagedNucleus'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SpacingBetweenSlices(NumericParameter):
    _name = 'SpacingBetweenSlices'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         units='mm',
                         range=(0, 1000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class TransmitCoilName(CategoricalParameter):
    _name = 'TransmitCoilName'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class AcquisitionMatrix(MultiValueNumericParameter):
    _name = 'AcquisitionMatrix'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SAR(NumericParameter):
    _name = 'SAR'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='W/kg',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SliceMeasurementDuration(NumericParameter):
    _name = 'SliceMeasurementDuration'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='s',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class GradientMode(CategoricalParameter):
    _name = 'GradientMode'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class FlowCompensation(CategoricalParameter):
    _name = 'FlowCompensation'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SliceResolution(NumericParameter):
    _name = 'SliceResolution'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=None,
                         acronym=ACRONYMS_IMG[self._name])


class ImagePositionPatient(MultiValueNumericParameter):
    _name = 'ImagePositionPatient'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=None,
                         acronym=ACRONYMS_IMG[self._name])


class PatientPosition(CategoricalParameter):
    _name = 'PatientPosition'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SliceLocation(NumericParameter):
    _name = 'SliceLocation'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SamplesPerPixel(NumericParameter):
    _name = 'SamplesPerPixel'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PhotometricInterpretation(CategoricalParameter):
    _name = 'PhotometricInterpretation'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class Rows(NumericParameter):
    _name = 'Rows'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class Columns(NumericParameter):
    _name = 'Columns'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PixelSpacing(MultiValueNumericParameter):
    _name = 'PixelSpacing'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='mm',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class BitsAllocated(NumericParameter):
    _name = 'BitsAllocated'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class BitsStored(NumericParameter):
    _name = 'BitsStored'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 100),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class HighBit(NumericParameter):
    _name = 'HighBit'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='',
                         range=(0, 100),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PixelRepresentation(NumericParameter):
    _name = 'PixelRepresentation'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='',
                         range=(0, 100),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class SmallestImagePixelValue(NumericParameter):
    _name = 'SmallestImagePixelValue'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class LargestImagePixelValue(NumericParameter):
    _name = 'LargestImagePixelValue'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class WindowCenter(NumericParameter):
    _name = 'WindowCenter'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class WindowWidth(NumericParameter):
    _name = 'WindowWidth'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         units='',
                         range=(0, 100000),
                         required=True,
                         severity='critical',
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class WindowCenterWidthExplanation(CategoricalParameter):
    _name = 'WindowCenterWidthExplanation'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class CoilString(CategoricalParameter):
    _name = 'CoilString'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PATMode(CategoricalParameter):
    _name = 'PATMode'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class PositivePCSDirections(CategoricalParameter):
    _name = 'PositivePCSDirections'

    def __init__(self, value=Unspecified):
        """Constructor"""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class VariableFlipAngleFlag(CategoricalParameter):
    _name = 'VariableFlipAngleFlag'

    def __init__(self, value=Unspecified):
        """Constructor."""

        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ImageOrientationPatient(MultiValueNumericParameter):
    _name = 'ImageOrientationPatient'

    def __init__(self, value=Unspecified):
        """Constructor."""
        if not isinstance(value, UnspecifiedType):
            value = list(value)

        super().__init__(name=self._name,
                         value=value,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name],
                         ordered=True)
        self.decimals = 0

    def __repr__(self):
        """repr"""

        name = self.acronym if self.acronym else self.name
        return f'{name}{self.get_value()})'

    def get_value(self):
        """getter"""
        if not isinstance(self._value, UnspecifiedType):
            # Add 0.0 will avoid -0.0
            return [0.0 + np.round(v, self.decimals) for v in self._value]
        return self._value

    def _compare_value(self, other, rtol=0, decimals=None):
        # Fix ImageOrientationPatient comparison to 0 decimals
        decimals = self.decimals

        for v, o in zip(self._value, other._value):
            # Numpy adds a warning : The default atol is not appropriate for
            # comparing numbers that
            # are much smaller than one (see Notes). Keeping relative tolerance
            # for now.
            # if not np.isclose(v, o, atol=1 ** -self.decimals):
            v = np.round(v, decimals=decimals)
            o = np.round(o, decimals=decimals)
            if not np.isclose(v, o, rtol=rtol):
                return False
        return True


class FieldOfView(CategoricalParameter):
    _name = 'FieldOfView'

    def __init__(self, value=Unspecified):
        """Constructor."""
        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=DICOM_TAGS[self._name],
                         acronym=ACRONYMS_IMG[self._name])


class ContentDate(CategoricalParameter):
    """Parameter specific class for BodyPartExamined"""

    _name = 'ContentDate'

    def __init__(self, value=Unspecified):
        """Constructor."""
        if not isinstance(value, UnspecifiedType):
            value = datetime.strptime(str(int(value)), '%Y%m%d')
        super().__init__(name=self._name,
                         value=value,
                         dtype=datetime,
                         dicom_tag=SESSION_TAGS[self._name],
                         acronym=ACRONYMS_DEMO[self._name])


class ContentTime(CategoricalParameter):
    """Parameter specific class for BodyPartExamined"""

    _name = 'ContentTime'

    def __init__(self, value=Unspecified):
        """Constructor."""
        # if not isinstance(value, UnspecifiedType):
        #     value = datetime.strptime(str(int(value)), '%Y%m%d')
        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=SESSION_TAGS[self._name],
                         acronym=ACRONYMS_DEMO[self._name])


class PatientSex(CategoricalParameter):
    """Parameter specific class for BodyPartExamined"""

    _name = 'PatientSex'

    def __init__(self, value=Unspecified):
        """Constructor."""
        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=SESSION_TAGS[self._name],
                         acronym=ACRONYMS_DEMO[self._name],
                         allowed_values=('M', 'F', 'O'))


class PatientWeight(NumericParameter):
    _name = 'PatientWeight'

    def __init__(self, value=Unspecified):
        """Constructor."""
        super().__init__(name=self._name,
                         value=value,
                         units='kg',
                         range=(0, 1e7),
                         required=False,
                         severity='critical',
                         dicom_tag=SESSION_TAGS[self._name],
                         acronym=ACRONYMS_DEMO[self._name])


class PatientSize(NumericParameter):
    _name = 'PatientSize'

    def __init__(self, value=Unspecified):
        """Constructor."""
        super().__init__(name=self._name,
                         value=value,
                         units='m',
                         range=(0, 1e7),
                         required=False,
                         severity='critical',
                         dicom_tag=SESSION_TAGS[self._name],
                         acronym=ACRONYMS_DEMO[self._name])


class OperatorsName(CategoricalParameter):
    _name = 'OperatorsName'

    def __init__(self, value=Unspecified):
        """Constructor."""
        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=SESSION_TAGS[self._name],
                         acronym=ACRONYMS_DEMO[self._name])


class InstitutionName(CategoricalParameter):
    _name = 'InstitutionName'

    def __init__(self, value=Unspecified):
        """Constructor."""
        super().__init__(name=self._name,
                         value=value,
                         dtype=str,
                         dicom_tag=SESSION_TAGS[self._name],
                         acronym=ACRONYMS_DEMO[self._name])


class SeriesNumber(NumericParameter):
    _name = 'SeriesNumber'

    def __init__(self, value=Unspecified):
        """Constructor."""
        super().__init__(name=self._name,
                         value=value,
                         units='NA',
                         range=(0, 1e7),
                         required=False,
                         severity='critical',
                         dicom_tag=SESSION_TAGS[self._name],
                         acronym=ACRONYMS_DEMO[self._name])


class PatientAge(NumericParameter):
    _name = 'PatientAge'

    # Prefer birthdate for age calculation
    # https://groups.google.com/g/comp.protocols.dicom/c/GvClri1CcWk # noqa

    def __init__(self, value=Unspecified):
        """Constructor"""
        value_years = Unspecified
        if not isinstance(value, UnspecifiedType):
            value_years = self.convert(value)

        super().__init__(name=self._name,
                         value=value_years,
                         units='Y',
                         range=(0, 999),
                         required=False,
                         severity='critical',
                         dicom_tag=SESSION_TAGS[self._name],
                         acronym=ACRONYMS_DEMO[self._name])

    def convert(self, value):
        age = value
        if isinstance(value, str):
            if len(value) > 1:
                unit = value[-1]
            else:
                raise ValueError("Invalid value in PatientAge")
            if unit == 'Y':
                age = int(value[:-1])
            elif unit == 'M':
                age = int(value[:-1]) / 12
            elif unit == 'D':
                age = int(value[:-1]) / 365
            else:
                raise ValueError("Invalid value in PatientAge")
        elif isinstance(value, int) or isinstance(value, float):
            age = value
        else:
            logger.error(f"Found age as {value}, which is not a valid type. "
                         f"Skipping.")
        return age


class MRImagingProtocol(BaseImagingProtocol):
    """Base class for all MR imaging protocols, including neuroimaging datasets
    """

    def __init__(self,
                 name="MRIProtocol",
                 category='MR',
                 filepath=None,
                 type=ProtocolType.INFERRED_FROM_DATASET):
        """constructor"""
        self.filepath = filepath
        self.type = type
        super().__init__(name=name, category=category)

        self._seq = dict()

    @property
    def category(self):
        return self._category

    def add(self, seq):
        """Adds a new sequence to the current protocol"""

        if not isinstance(seq, BaseSequence):
            raise TypeError(
                'Invalid type! Must be a valid instance of BaseSequence')

        if seq.name in self._seq:
            raise ValueError(
                'This sequence already exists! Double check or rename!')

        self._seq[seq.name] = seq

    def get_sequence_ids(self):
        """Returns the list of sequence ids in the protocol"""
        return list(self._seq.keys())

    def __bool__(self):
        """Checks if the protocol is empty"""

        if len(self._seq) < 1:
            return False
        else:
            return True

    def __getitem__(self, name):
        """getter"""

        try:
            return self._seq[name]
        except KeyError:
            raise KeyError(f'{name} has not been set yet')

    @staticmethod
    def _get_value_and_unit(v):
        value, unit = v, None
        if v.endswith('ms'):
            value, unit = v.split('ms')[0], 'ms'
        elif v.endswith('mm'):
            value, unit = v.split('mm')[0], 'mm'
        elif v.endswith('deg'):
            value, unit = v.split('deg')[0], 'deg'
        elif v.endswith('Hz/Px'):
            value, unit = v.split('Hz/Px')[0], 'Hz/Px'
        elif v.endswith('%'):
            value, unit = v.split('%')[0], '%'
        return value.strip(), unit

    def add_sequence_from_dict(self, seq_name, param_dict):
        """
        Adds a sequence to the protocol from a dictionary
        """
        seq = ImagingSequence(name=seq_name)
        seq.from_dict(param_dict)
        self.add(seq)

    def compliant(self, other, rtol=0, decimals=None, include_params=None,
                  include_sequences=None):
        """Checks if the current protocol is compliant with another protocol"""

        if not isinstance(other, MRImagingProtocol):
            raise TypeError(
                'Invalid type! Must be a valid instance of MRImagingProtocol')

        if include_params is None:
            include_params = []

        # check if the sequences are the same
        if set(self.get_sequence_ids()) != set(other.get_sequence_ids()):
            logger.info(
                f'Sequences are not the same! {self.get_sequence_ids()} '
                f'vs {other.get_sequence_ids()}')
            return False, None

        non_compliant_sequences = []

        if include_sequences is None:
            include_sequences = self.get_sequence_ids()

        # check if the parameters are the same
        for seq_id in include_sequences:
            try:
                this_seq = self[seq_id]
                that_seq = other[seq_id]
            except KeyError:
                # If the sequence is not found in either of the protocols,
                #   skip it and move on to the next one.
                logger.info(f'{seq_id} not found in either '
                            f'of the protocols <{self, other}>')
                continue

            compliant = this_seq.compliant(that_seq, rtol, decimals,
                                           include_params)
            if not compliant:
                non_compliant_sequences.append((this_seq, that_seq))

        bool_flag = len(non_compliant_sequences) < 1
        return bool_flag, non_compliant_sequences

    def __eq__(self, other):
        """equivalence operator"""

        bool_flag, _ = self.compliant(other)
        return bool_flag


class SiemensMRImagingProtocol(MRImagingProtocol):
    def __init__(self, name='SiemensMRProtocol',
                 category='MR',
                 filepath=None,
                 type=ProtocolType.USER_DEFINED,
                 program_name=None,
                 convert_ped=True):
        super().__init__(name=name, category=category, filepath=filepath,
                         type=type)
        self.programs = {}
        self.header_title = None
        self._parameter_map = {
            'PhaseEncodingDirection': ['Routine', 'Phase enc. dir.'],
            'EchoTime': ['Routine', 'TE'],
            'RepetitionTime': ['Routine', 'TR'],
            'FlipAngle': ['Contrast - Common', 'Flip angle'],
            'ParallelAcquisitionTechnique': ['Resolution - iPAT',
                                             'Accel. mode'],
            'MultiSliceMode': ['Sequence - Part 1', 'Multi-slice mode'],
            'PixelBandwidth': ['Sequence - Part 1', 'Bandwidth'],
            'ReceiveCoilActiveElements': ['Routine', 'Coil elements'],
            'InversionTime': ['Contrast - Common', 'TI'],
            'MRAcquisitionType': ['Sequence - Part 1', 'Dimension'],
            'PercentPhaseFOV': ['Geometry - Common', 'FoV phase'],
            'NumberOfAverages': ['Routine', 'Averages'],
            'SliceThickness': ['Geometry - Common', 'Slice thickness'],
        }
        self.program_name = program_name

        # If PED is A >> P or P >> A, R >> L or L >> R, then use this flag to
        # convert to ROW/COL
        # This is because DICOM tags are ROW/COL, but Siemens uses A >> P, R >> L
        self.convert_ped = convert_ped
        if filepath is not None:
            self.from_xml(filepath)
            self._add_sequences_from_file()

    def _add_sequences_from_file(self):
        if self.program_name is None:
            # there is more than one protocol file in the XML
            # specify the number of protocol
            # we are taking the first one, assuming it is the latest
            self.program_name = list(self.programs.keys())[0]
            # raise ValueError('Program name not set. Use set_program_name() to
            # set it')
        for sequence_name in self.programs[self.program_name].keys():
            seq = DicomImagingSequence(name=sequence_name)
            parameters = {}
            for param_name in self._parameter_map.keys():
                parameters[param_name] = self._get_parameter(sequence_name,
                                                             param_name)
            seq.from_dict(parameters)
            self.add(seq)

    def set_program_name(self, program_name):
        self.program_name = program_name

    def add_to_map(self, parameter_name, access_keys):
        self._parameter_map[parameter_name] = access_keys

    def get_program_names(self):
        return self.programs.keys()

    def _get_parameter(self, sequence_name, parameter_name):
        def get_value(programs, program_name, sequence_name, access_keys):
            # recursively get the value
            access_keys = deepcopy(access_keys)
            root_ = programs[program_name][sequence_name]
            while access_keys:
                key = access_keys.pop(0)
                try:
                    root_ = root_[key]
                except KeyError as e:
                    logger.info(
                        f'Parameter not found in the sequence {sequence_name}.')
                    raise e
            return root_

        if self.program_name is None:
            raise ValueError(
                'Program name not set. Use set_program_name() to set it')

        try:
            access_keys = self._parameter_map[parameter_name]
            value = get_value(self.programs, self.program_name, sequence_name,
                              access_keys)
        except KeyError:
            logger.info(f'Parameter not found : {parameter_name}')
            return Unspecified

        # convert PED to DICOM tags
        if parameter_name == 'PhaseEncodingDirection' and self.convert_ped:
            if value == 'A >> P' or value == 'P >> A':
                return 'COL'
            if value == 'R >> L' or value == 'L >> R':
                return 'ROW'
        else:
            return value

    def is_valid_xml(self, filepath=None):
        """Checks if the XML file is valid"""
        if not filepath.exists():
            raise FileNotFoundError(f'File {filepath} does not exist')
        # check if the file is an XML file
        if not filepath.suffix == '.xml':
            raise ValueError(f'File {filepath} is not an XML file')

    def _collect_sequences_by_program(self, child):
        """Collects the sequence names by program name"""
        toc = child.TOC.root.region.NormalExam_dot_engine.getchildren()
        for program in toc:
            prog_name = program.get('name')
            self.programs[prog_name] = {}
            # get the sequences for each program
            for protocol in program.getchildren():
                seq_name = convert2ascii(protocol.get('name'))
                self.programs[prog_name][seq_name] = dict(protocol.attrib)

    def _collect_parameters(self, card, cards_dict):
        """Collects the parameters by card"""
        if card.tag != 'Card':
            return cards_dict
        for parameter in card.getchildren():
            label = parameter.Label.text.strip()
            # TODO: Also add unit to the reference protocol
            text = parameter.ValueAndUnit.text.strip()
            value, unit = self._get_value_and_unit(text)
            card_id = card.get('name')
            if card_id not in cards_dict:
                cards_dict[card_id] = {}
            cards_dict[card_id][label] = auto_convert(value)
        return cards_dict

    def from_xml(self, filepath=None):
        """
        A function to parse the XML file and extract the parameters for
        each sequence
        """
        # check if the file exists
        if filepath is None:
            filepath = self.filepath
        filepath = Path(filepath)

        self.is_valid_xml(filepath)

        # read the tree
        tree = objectify.parse(filepath)
        # get the root
        root = tree.getroot()
        # get the header title, which is the name of the scanner
        # it is not used, but saved for future
        self.header_title = root.PrintTOC.TOC.HeaderTitle

        # there are two types of children in the root
        # 1. PrintTOC : this is the table of contents
        # 2. PrintProtocol : this is the actual protocol
        for child in root.getchildren():
            if child.tag == 'PrintTOC':
                self._collect_sequences_by_program(child)
            elif child.tag == 'PrintProtocol':
                # The protocol is organized into cards. Each card contains a set
                # of parameters
                protocol = child.Protocol
                for step in protocol.getchildren():
                    if step.tag != 'SubStep':
                        continue

                    hdr_path = step.ProtHeaderInfo.HeaderProtPath.text
                    hdr_property = step.ProtHeaderInfo.HeaderProperty.text

                    prog_name = hdr_path.split('\\')[-2]
                    seq_name = convert2ascii(hdr_path.split('\\')[-1])
                    cards_dict = self.programs[prog_name][seq_name]
                    cards_dict['header_property'] = hdr_property
                    for card in step.getchildren():
                        cards_dict = self._collect_parameters(card, cards_dict)


class ImagingSequence(BaseSequence, ABC):
    def __init__(self,
                 name='MRI',
                 dicom=None,
                 imaging_params=None,
                 required_params=None,
                 store_demographics=True,
                 path=None, ):
        """constructor"""

        self.multi_echo = False
        self.params_classes = []
        self.parameters = set(ACRONYMS_IMG.keys())
        self.store_demographics = store_demographics
        self.demographics = set(ACRONYMS_DEMO.keys())
        super().__init__(name=name, path=path)

    def add_parameter(self, pname, value, module='protocol.imaging'):
        """
        Adds a new parameter to the sequence.

        Parameters
        ----------
        pname : str
            Name of the parameter
        value : object
            Value of the parameter
        module : str
            Name of the module where the parameter class is defined
        """
        param_cls_name = f'{module}.{pname}'

        try:
            param_cls = self.import_string(param_cls_name)
        except ImportError:
            raise ImportError(f'Parameter {pname} is not '
                              f'supported yet. '
                              f'Please raise a issue on GitHub.')

        try:
            param = param_cls(value)
        except (TypeError, ValueError):
            param = param_cls(Invalid)
        self.add(param)

    def _init_param_classes(self):
        """
        Initializes the parameter classes for the sequence.
        """
        for p in self.parameters:
            param_cls_name = f'protocol.imaging.{p}'
            try:
                cls_object = self.import_string(param_cls_name)
            except ImportError:
                raise ImportError(f'Parameter {param_cls_name} is not '
                                  f'supported yet. '
                                  f'Please raise a issue on GitHub.')
            self.params_classes.append(cls_object)

    def from_dict(self, params_dict):
        """
        Populates the sequence parameters from a dictionary.

        Parameters
        ----------
        params_dict : dict
            Dictionary containing the parameter names and values as key, value pairs.
        """
        self.parameters = set(params_dict.keys())

        for pname, value in params_dict.items():
            if isinstance(value, float) and np.isnan(value):
                value = Unspecified

            if isinstance(value, BaseParameter):
                self[pname] = value
            else:
                self.add_parameter(pname, value)

    @staticmethod
    def import_string(dotted_path):
        """
        Import a dotted module path and return the attribute/class designated by
        the last name in the path. Raise ImportError if the import failed.
        """

        # TODO: if not able to search for the module, then find the class
        #  by comparing all classes in lowercase.
        #  If found, then return the class

        # check if it is a valid module path
        try:
            module_path, class_name = dotted_path.rsplit(".", 1)
        except ValueError as err:
            raise ImportError(
                "%s doesn't look like a module path" % dotted_path) from err

        # if the parameter class exists with an alternative name in the module
        if class_name in ANALOGUES_DICT:
            class_name = ANALOGUES_DICT[class_name]

        # import module : protocol.imaging
        module = import_module(module_path)

        try:
            # directly try if the parameter class exists
            return getattr(module, class_name)
        except AttributeError:
            # if not, search for appropriate parameter class in the module
            for name, cls in module.__dict__.items():
                if name.lower() == class_name.lower() \
                        and issubclass(cls, BaseParameter):
                    return getattr(module, name)

        # didn't find an appropriate class raise error
        raise ImportError(
            'Module "%s" does not define a "%s" attribute/class'
            % (module_path, class_name)
        )


class BidsImagingSequence(ImagingSequence):
    """
    Class representing an Imaging sequence for BIDS datasets

    Parameters
    ----------
    bidsfile : Path or str
        Path to the BIDS JSON file
    name : str
        Name of the sequence
    path : Path or str
        Path to the folder containing the files
    """

    def __init__(self, bidsfile=None, name='MRI',
                 path=None):
        """constructor"""
        super().__init__(name=name, path=path)
        self.non_empty_flag = False
        self.img_paths = None
        if path:
            self.set_img_path(path)

        self.invalid_parameters = []
        self.unsupported_parameters = []

        if bidsfile is not None:
            self.parse(bidsfile)

    def set_session_info(self, name, subject_id, session_id, run_id):
        """
        Sets the session information.

        Parameters
        ----------
        name : str
            Name of the sequence
        subject_id : str
            Subject ID
        session_id : str
            Session ID
        run_id : str
            Run ID

        """
        self.name = name
        self.subject_id = subject_id
        self.session_id = session_id
        self.run_id = run_id

    def set_img_path(self, path):
        """
        Stores the path to the image files

        Parameters
        ----------
        path : Path
            Path to the image files

        """
        self.img_paths = list(path.glob('*.nii*'))

    def parse(self, bidsfile, params=None):
        """Parses the parameter values from a given BIDS JSON object or file."""
        bidsfile = Path(bidsfile)

        if not bidsfile.exists():
            raise IOError('input bids file path does not exist!')
        bidsdata = read_json(bidsfile)

        for pname in bidsdata.keys():
            if pname in INVALID_PARAMETERS:
                self.invalid_parameters.append(pname)
                continue
            # check if an alternative name for the class exists
            pname_alter = ANALOGUES_DICT.get(pname, pname)
            value = get_bids_param_value(bidsdata, pname)

            try:
                self.add_parameter(pname_alter, value)
                # If even one parameter was added, the non_empty_flag
                #  will be set to True
                self.non_empty_flag = True
            except ImportError:
                # if the parameter class does not exist, log the error
                # and continue to the next parameter
                self.unsupported_parameters.append(pname)

    def is_valid(self):
        """
        Checks if the sequence is valid

        JSON files don't have any standard. Therefore, it is possible that
        non of the parameters specified in the config are available in the JSON
        file. In such cases, we will return False.
        """

        if len(self.invalid_parameters) > 0:
            logger.warning(f'Invalid parameters found : '
                           f'{self.invalid_parameters}')
        if len(self.unsupported_parameters) > 0:
            logger.warning(f'Following parameters are not supported yet.'
                           f' Please raise an issue on GitHub : '
                           f'{self.unsupported_parameters}')
        if not self.non_empty_flag:
            logger.warning('None of the parameters found in the JSON file'
                           'are supported/valid. Please check the JSON file.')
        return self.non_empty_flag


class DicomImagingSequence(ImagingSequence):
    """Class representing an Imaging sequence

    Although we would use it mostly for MR imaging sequences to start with
    it should be able to store any sequence captured by DICOM: CT, XRAY etc
    """

    def __init__(self,
                 dicom=None,
                 name='MRI',
                 imaging_params=None,
                 required_params=None,
                 store_demographics=True,
                 path=None, ):
        """constructor"""

        self.multi_echo = False
        self.params_classes = []
        self.parameters = set(ACRONYMS_IMG.keys())
        self.store_demographics = store_demographics
        self.demographics = set(ACRONYMS_DEMO.keys())
        super().__init__(name=name, path=path)

        if self.parameters:
            self._init_param_classes()
        if dicom is not None:
            self.parse(dicom)
            self._parse_private(dicom)
            self.set_session_info(dicom)
            self.collect_demographics(dicom)

    def compare_subset_params(self, other):
        """
        Compares the parameters of the current sequence with another sequence. The
        function compares a subset of parameters that are subject to variation e.g. EchoTime
        Comparing all parameters is slow and might not be required.

        For ex. while comparing slice, we just need to compare parameters that are known
        to be variable e.g. EchoTime, EchoNumber etc. We don't need to compare all parameters
        like SliceLocation, SliceThickness.

        Parameters
        ----------
        other : BaseSequence
            The other sequence to compare with

        Returns
        -------
        bool
            True if the parameters match, False otherwise
        """
        if not isinstance(other, BaseSequence):
            raise TypeError('Input must be a valid BaseSequence object')
        for parameter in ['EchoTime', 'EchoNumber']:
            if not self[parameter].compliant(other[parameter]):
                return False
        return True

    def set_session_info(self, dicom):
        """
        Sets the session information from the DICOM header. This is used to
        set the session_id, subject_id, run_id and timestamp
        """
        if not isinstance(dicom, pydicom.FileDataset):
            raise TypeError('Input must be a pre-read pydicom object.')

        #   name: SeriesNumber_Suffix
        #   priority order: SeriesDescription, SequenceName, ProtocolName
        self.name = get_sequence_name(dicom)
        self.subject_id = str(dicom.get('PatientID', None))
        # series number is a proxy for session?
        self.series_number = str(dicom.get('SeriesNumber', None))
        self.session_id = str(dicom.get('StudyInstanceUID', None))
        self.run_id = dicom.get('SeriesInstanceUID', None)
        date = dicom.get('ContentDate', None)
        # time = dicom.get('ContentTime', None)
        # TODO: time format varies across datasets. Find a way to
        #   reconcile differences and use it in timestamp
        if not isinstance(date, UnspecifiedType):
            datetime_obj = datetime.strptime(date, '%Y%m%d')
            self.timestamp = datetime_obj

    def collect_demographics(self, dicom):
        if self.store_demographics:
            for pname in self.demographics:
                value = get_dicom_param_value(dicom, pname,
                                              tag_dict=SESSION_TAGS)
                self.add_parameter(pname, value)

    def parse(self, dicom, params=None):
        """Parses the parameter values from a given DICOM object or file."""
        if self.parameters is None:
            if params is None:
                raise ValueError('imaging_params must be provided either during'
                                 ' initialization or during parse() call')
            else:
                self._init_param_classes()

        if not isinstance(dicom, pydicom.FileDataset):
            if not isinstance(dicom, Path):
                raise ValueError('Input must be a pydicom FileDataset or Path')
            else:
                if not dicom.exists():
                    raise IOError('input dicom path does not exist!')
                dicom = pydicom.dcmread(dicom)

        for pname in self.parameters:
            # pname = param_class._name
            value = get_dicom_param_value(dicom, pname)
            self.add_parameter(pname, value)

    def _parse_private(self, dicom):
        """vendor specific private headers"""

        if header_exists(dicom):
            csa_header, csa_values = parse_csa_params(dicom)
            for name, val in csa_values.items():
                if name in self.parameters:
                    self.add_parameter(name, val)
        else:
            logger.info('No private header found in DICOM file')
            # TODO: throw a warning when expected header doesnt exist
            # TODO: warn if specific parameter couldn't be read or queryable etc

    def _check_compliance(self, this_param, that_param, rtol, decimals=None):
        if isinstance(this_param, NumericParameter) or \
                isinstance(this_param, MultiValueNumericParameter):
            compliant = this_param.compliant(that_param, rtol=rtol,
                                             decimals=decimals)
        elif isinstance(this_param, ReceiveCoilActiveElements):
            bpe = self['BodyPartExamined'].get_value()
            compliant = this_param.compliant(that_param,
                                             body_part_examined=bpe)
        else:
            compliant = this_param.compliant(that_param)
        return compliant

    def set_echo_times(self, echo_times, echo_number=None):
        """Sets the echo times for a multi-echo sequence."""

        self.multi_echo = len(echo_times) > 1

        try:
            self['EchoTime'] = MultiValueEchoTime(echo_times)
        except (TypeError, ValueError):
            self['EchoTime'] = MultiValueEchoTime(Invalid)

        if echo_number is not None:
            try:
                self['EchoNumber'] = MultiValueEchoNumber(echo_number)
            except (TypeError, ValueError):
                self['EchoNumber'] = MultiValueEchoNumber(Invalid)
