# -*- coding: utf-8 -*-

"""Main module containing the core classes."""

from abc import ABC, abstractmethod
from collections.abc import MutableMapping
from numbers import Number
from pathlib import Path
from typing import Iterable, Union

import numpy as np

from protocol import logger
from protocol.config import (SUPPORTED_IMAGING_MODALITIES,
                             Unspecified, UnspecifiedType)
from protocol.utils import convert2ascii


# A [imaging] Parameter is a container class for a single value, with a name
#       with methods to check for compliance and validity
# A [imaging] Sequence is defined as a set of parameters
#       implemented as a dict
# A [Sequence] Protocol is an unmutable Sequence for reference
# An Imaging Protocol is an ordered sequence of Sequences for a single session
#       although their order isn't used or checked in any way


class BaseParameter(ABC):
    """
    Base class for all parameters. A parameter is a container class for a single
    value (or a list of values), with a name, with methods to check for compliance
    and validity. For example, a parameter may represent imaging acquisition
    parameters of a sequence, e.g. RepetitionTime, EchoTime,
    PhaseEncodingDirection, etc.

    Parameters
    ----------
    name : str
        Name of the parameter.
    value : object
        Value of the parameter.
    dtype : type
        Data type of the parameter.
    units : str
        Units of the parameter. For example, 'ms' for milliseconds, 's' for
        seconds, etc.
    steps : int
        Incremental steps of the parameter. For example, 10 for a parameter that
        can take
        values such as 10, 20, 30, 40, etc.
    range : tuple
        Range of the parameter. For example, (0, 100) for a parameter that can
        take values
        between 0 and 100.
    required : bool
        Whether the parameter is required or not.
    severity : str
        Importance of the parameter. For example, 'critical' for a parameter that is
        critical for acquisition, 'optional' for a parameter that is optional for
        acquisition.
    dicom_tag : str
        DICOM tag of the parameter. For example, '0018,0080' for RepetitionTime.
    acronym : str
        Acronym of the parameter. For example, 'TR' for RepetitionTime.
    """

    def __init__(self,
                 name='parameter',
                 value=Unspecified,
                 dtype=None,
                 units='ms',
                 steps=1,
                 range=None,
                 required=True,
                 severity='critical',
                 dicom_tag=None,
                 acronym=None):
        """constructor"""

        self.required = required
        self.severity = severity

        self._value = value
        self.dtype = dtype
        self.units = units
        self.range = range
        self.steps = steps
        name = convert2ascii(name)
        if not name:
            raise ValueError('Parameter name cannot be empty!')
        self.name = convert2ascii(name)
        self.acronym = acronym
        self.dicom_tag = dicom_tag

        self.decimals = 2  # numerical tolerance in decimal places

    def get_value(self):
        """Getter for the value of the parameter."""
        return self._value

    def compliant(self, other, **kwargs):
        """
        Method to check if one parameter value is compatible w.r.t another,
        either in equality or within acceptable range, for that data type.

        Parameters
        ----------
        other : BaseParameter
            The other parameter to compare with.
        kwargs : Any
            Additional keyword arguments to be passed.

        """

        # TODO: if self(reference) is UnspecifiedType, return True. This is to allow
        #  for a parameter to be optional, but if self(reference) is specified,
        #  and other is not, return False.
        if isinstance(self._value, UnspecifiedType) or isinstance(other._value,
                                                                  UnspecifiedType):
            logger.debug(f'one of the values being compared is UnspecifiedType'
                         f'in {self.name}')
            return True
        # elif isinstance(other.value, UnspecifiedType):
        #     return False
        else:
            # type() returns the immediate class of the object. Of course,
            # both are BaseParameter, but we need to check if they are the same
            # subclass of BaseParameter
            if type(other) is type(self):
                return self._check_compliance(other, **kwargs)
            else:
                raise TypeError(f'Cannot compare {type(self)} with {type(other)}')

    @abstractmethod
    def _check_compliance(self, other, **kwargs):
        """Method to check if one parameter value is compatible w.r.t another,
            either in equality or within acceptable range, for that data type.
        """

    @abstractmethod
    def _compare_value(self, other, **kwargs):
        """
        Method to compare the values of two parameters
        """

    @abstractmethod
    def _compare_units(self, other):
        """
        Method to compare the units of two parameters
        """

    def __eq__(self, other):
        """equality is defined as compliance here"""

        return self.compliant(other)

    def __hash__(self):
        return hash(self.__repr__())

    def __repr__(self):
        """repr"""

        name = self.acronym if self.acronym else self.name
        return f'{name}({self.get_value()})'

    def __str__(self):
        return self.__repr__()


class MultiValueNumericParameter(BaseParameter):
    """
    Parameter subclass for parameters that can take multiple values, such as
    EchoTime, ImageOrientationPatient etc.

    Parameters
    ----------
    name : str
        Name of the parameter.
    value : object
        Value of the parameter.
    units : str
        Units of the parameter. For example, 'ms' for milliseconds, 's' for
        seconds, etc.
    steps : int
        Incremental steps of the parameter. For example, 10 for a parameter that
        can take values such as 10, 20, 30, 40, etc.
    range : tuple
        Range of the parameter. For example, (0, 100) for a parameter that can
        take values
        between 0 and 100.
    required : bool
        Whether the parameter is required or not.
    severity : str
        Importance of the parameter. For example, 'critical' for a parameter that is
        critical for acquisition, 'optional' for a parameter that is optional for
        acquisition.
    dicom_tag : str
        DICOM tag of the parameter. For example, '0018,0080' for RepetitionTime.
    acronym : str
        Acronym of the parameter. For example, 'TR' for RepetitionTime.
    ordered : bool
        Whether the parameter values are ordered or not. Some array types don't
        have any order like SequenceName, and SequenceVariant. Therefore,
        ordered=False. as the values can be sorted. But others like
        ImageOrientation, ShimSetting etc. have an order, they cannot be sorted.
        Therefore, ordered=True.
    """

    def __init__(self,
                 name,
                 value,
                 dicom_tag=None,
                 acronym=None,
                 units=None,
                 range=None,
                 steps=None,
                 required=True,
                 severity='critical',
                 ordered=False):
        """
        Constructor.
        some array types don't have any order like EchoTime, and EchoNumber. So
        they can be sorted. But others cannot like ImageOrientation, ShimSetting
        etc. have an order, they cannot be sorted.
        """

        super().__init__(name=name,
                         value=value,
                         dtype=Number,
                         units=units,
                         range=range,
                         steps=steps,
                         required=required,
                         severity=severity,
                         dicom_tag=dicom_tag,
                         acronym=acronym)

        if not isinstance(value, UnspecifiedType):
            if isinstance(value, Iterable):
                if not all([isinstance(v, self.dtype) for v in value]):
                    raise TypeError(f'Input {value} is not of type {self.dtype}'
                                    f' for {self.name}')
                self._value = [float(v) for v in value]

            elif isinstance(value, self.dtype):
                self._value = [float(value)]
            else:
                raise TypeError(f'Input {value} is not of type {self.dtype} for'
                                f' {self.name}')
            if not ordered:
                self._value = sorted(self._value)
        # overriding default from parent class
        self.decimals = 3

    def get_value(self):
        """
        Getter for the value of the parameter. If the parameter has only one value,
        return that value, else return the list of values.
        """
        if isinstance(self._value, UnspecifiedType):
            return self._value
        if len(self._value) == 1:
            return self._value[0]
        else:
            return self._value

    def _check_compliance(self, other, rtol=0, decimals=None):
        """Method to check if one parameter value is compatible w.r.t another,
            either in equality or within acceptable range, for that data type.
        """
        if decimals is None:
            decimals = self.decimals
        return self._compare_value(other, rtol=rtol, decimals=decimals) and \
            self._compare_units(other)

    def _compare_value(self, other, rtol=0, decimals=None):
        """Method to compare the values of two parameters"""
        if decimals is None:
            decimals = self.decimals

        # tolerance is 1e-N where N = self.decimals
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

    def _compare_units(self, other):
        # TODO: implement unit conversion
        return self.units == other.units


class NumericParameter(BaseParameter):
    """Parameter specific class for Numeric parameters such as RepetitionTime etc.

    Parameters
    ----------
    name : str
        Name of the parameter.
    value : object
        Value of the parameter.
    units : str
        Units of the parameter. For example, 'ms' for milliseconds, 's' for
        seconds, etc.
    steps : int
        Incremental steps of the parameter. For example, 10 for a parameter that
        can take
        values such as 10, 20, 30, 40, etc.
    range : tuple
        Range of the parameter. For example, (0, 100) for a parameter that can
        take values
        between 0 and 100.
    required : bool
        Whether the parameter is required or not.
    severity : str
        Importance of the parameter. For example, 'critical' for a parameter that is
        critical for acquisition, 'optional' for a parameter that is optional for
        acquisition.
    dicom_tag : str
        DICOM tag of the parameter. For example, '0018,0080' for RepetitionTime.
    acronym : str
        Acronym of the parameter. For example, 'TR' for RepetitionTime.
    """

    def __init__(self,
                 name,
                 value,
                 dicom_tag=None,
                 acronym=None,
                 units=None,
                 range=None,
                 steps=None,
                 required=True,
                 severity='critical', ):
        """Constructor."""

        super().__init__(name=name,
                         value=value,
                         dtype=Number,
                         units=units,
                         range=range,
                         steps=steps,
                         required=required,
                         severity=severity,
                         dicom_tag=dicom_tag,
                         acronym=acronym)

        if not isinstance(value, UnspecifiedType):
            if not isinstance(value, self.dtype):
                raise TypeError(f'Input {value} is not of type {self.dtype} for'
                                f' {self.name}')
            if np.isnan(value):
                raise ValueError(f'Input {value} is not a valid number for '
                                 f'{self.name}')
            self._value = float(value)

        # overriding default from parent class
        self.decimals = 3

    def _check_compliance(self, other, rtol=0, decimals=None):
        """Method to check if one parameter value is compatible w.r.t another,
            either in equality or within acceptable range, for that data type.
        """
        if not decimals:
            decimals = self.decimals
        return self._compare_value(other, rtol=rtol, decimals=decimals) and \
            self._compare_units(other)

    def _compare_value(self, other, rtol=0, decimals=None):
        if decimals is None:
            decimals = self.decimals

        # tolerance is 1e-N where N = self.decimals
        # Numpy adds a warning : The default atol is not appropriate for comparing
        # numbers that
        # are much smaller than one (see Notes). Keeping relative tolerance for now.
        # if np.isclose(self._value, other._value, atol=1 ** -self.decimals):
        v = np.round(self._value, decimals=decimals)
        o = np.round(other._value, decimals=decimals)
        if np.isclose(v, o, rtol=rtol):
            return True
        else:
            return False

    def _compare_units(self, other):
        # TODO: implement unit conversion
        return self.units == other.units


class MultiValueCategoricalParameter(BaseParameter):
    """
    Parameter specific class for parameters that can take multiple string values,
    such as e.g., SequenceVariant = ['SK', 'SP'],
    ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL'] etc.

    Parameters
    ----------
    name : str
        Name of the parameter.
    value : object
        Value of the parameter.
    dtype : type
        Data type of the parameter.
    units : str
        Units of the parameter. For example, 'ms' for milliseconds, 's' for
        seconds, etc.
    range : tuple
        Range of the parameter. For example, (0, 100) for a parameter that can
        take values
        between 0 and 100.
    required : bool
        Whether the parameter is required or not.
    severity : str
        Importance of the parameter. For example, 'critical' for a parameter that is
        critical for acquisition, 'optional' for a parameter that is optional for
        acquisition.
    dicom_tag : str
        DICOM tag of the parameter. For example, '0018,0080' for RepetitionTime.
    acronym : str
        Acronym of the parameter. For example, 'TR' for RepetitionTime.
    allowed_values : tuple
        Valid values for the parameter.
    """

    def __init__(self,
                 name,
                 value,
                 dicom_tag=None,
                 acronym=None,
                 dtype=Iterable,
                 required=True,
                 severity='critical',
                 units=None,
                 range=None,
                 allowed_values=tuple()):

        """Constructor."""

        super().__init__(name=name,
                         value=value,
                         dtype=dtype,
                         units=units,
                         range=range,
                         required=required,
                         severity=severity,
                         dicom_tag=dicom_tag,
                         acronym=acronym)

        self.allowed_values = allowed_values
        if not isinstance(value, UnspecifiedType):
            if not isinstance(value, self.dtype):
                try:
                    value = list(value)
                except TypeError:
                    raise TypeError(f'Got input {value} of type {type(value)}. '
                                    f'Expected {self.dtype} for {self.name}')
            if isinstance(value, str):
                # strip whitespaces if any
                value = "".join(value.split())
                if value:
                    self._value = [value.upper()]
                else:
                    self._value = Unspecified
            else:
                self._value = [str(v).upper() for v in value]

            # if allowed_values is set, check if input value is allowed
            if self.allowed_values and (value not in self.allowed_values):
                raise ValueError(f'Invalid value for {self.name}. Got {value} '
                                 f'Must be one of {self.allowed_values}')

    def _check_compliance(self, other, **kwargs):
        """Method to check if one parameter value is compatible w.r.t another,
            either in equality or within acceptable range, for that data type.
        """
        # TODO we need to be able to convert units before comparison
        return self._compare_value(other) and self._compare_units(other)

    def _compare_units(self, other):
        # TODO: implement unit conversion
        return self.units == other.units

    def _compare_value(self, other, **kwargs):
        if isinstance(other._value, self.dtype):
            value_to_compare = other._value
        else:
            raise TypeError(f'Invalid type. Must be an instance of '
                            f'{self.dtype} or {self}')
        return set(self._value) == set(value_to_compare)


class CategoricalParameter(BaseParameter):
    """
    Parameter specific class for parameters that can take a single string value,
    such as SeriesDescription, ProtocolName, PhaseEncodingDirection etc.

    Parameters
    ----------
    name : str
        Name of the parameter.
    value : object
        Value of the parameter.
    dtype : type
        Data type of the parameter.
    units : str
        Units of the parameter. For example, 'ms' for milliseconds, 's' for
        seconds, etc.
    dicom_tag : str
        DICOM tag of the parameter. For example, '0018,0080' for RepetitionTime.
    acronym : str
        Acronym of the parameter. For example, 'TR' for RepetitionTime.
    required : bool
        Whether the parameter is required or not.
    severity : str
        Importance of the parameter. For example, 'critical' for a parameter that is
        critical for acquisition, 'optional' for a parameter that is optional for
        acquisition.
    allowed_values : tuple
        Valid values for the parameter.
    """

    def __init__(self,
                 name,
                 value,
                 dicom_tag=None,
                 acronym=None,
                 dtype=str,
                 required=True,
                 severity='critical',
                 units=None,
                 allowed_values=tuple()):

        """Constructor."""

        super().__init__(name=name,
                         value=value,
                         dtype=dtype,
                         units=units,
                         required=required,
                         severity=severity,
                         dicom_tag=dicom_tag,
                         acronym=acronym)

        self.allowed_values = allowed_values
        if not isinstance(value, UnspecifiedType):
            if value is None:
                raise ValueError(f'Got NoneType, Expected {dtype}.')
            if not isinstance(value, self.dtype):
                try:
                    value = self.dtype(value)
                except TypeError:
                    raise TypeError(f'Got input {value} of type {type(value)}. '
                                    f'Expected {self.dtype} for {self.name}')

            if isinstance(value, str):
                # strip whitespaces if any
                value = "".join(value.split())
                if value:
                    self._value = value.upper()
                else:
                    self._value = Unspecified

            # if allowed_values is set, check if input value is allowed
            if self.allowed_values and (value not in self.allowed_values):
                raise ValueError(f'Invalid value for {self.name}. Got {value} '
                                 f'Must be one of {self.allowed_values}')

    def _check_compliance(self, other, **kwargs):
        """Method to check if one parameter value is compatible w.r.t another,
            either in equality or within acceptable range, for that data type.
        """
        return self._compare_value(other) and self._compare_units(other)

    def _compare_units(self, other):
        # TODO: implement unit conversion
        return self.units == other.units

    def _compare_value(self, other, **kwargs):
        if isinstance(other, type(self)):
            value_to_compare = other._value
        elif isinstance(other, self.dtype):
            value_to_compare = other
        else:
            raise TypeError(f'Invalid type. Must be an instance of '
                            f'{self.dtype} or {self}')

        return self._value == value_to_compare


class BaseSequence(MutableMapping):
    """
    Container to capture imaging parameter values for a given sequence. A sequence
    is defined as a set of parameters implemented as a dict. A sequence is
    mutable, i.e. parameters and their values can be modified.

    Parameters
    ----------
    name : str
        Name of the sequence.
    params : set
        A set of parameters in the sequence.
    path : Path | str
        Path to the sequence on disk.

    Examples
    --------

    .. code :: python

        from protocol import BaseSequence, BaseParameter
        # adding a parameter to a sequence
        seq = BaseSequence()
        parameter = BaseParameter(name='RepetitionTime', value=2.0)
        seq.add(parameter)

        # Checking if parameters of two sequences are same
        if seq1.compliant(seq2):
            # they are compliant
        else:
            # not compliant

        # Retrieving a parameter value
        param = seq['RepetitionTime']
        # print the value
        print(param.get_value())
    """

    def __init__(self,
                 name: str = 'Sequence',
                 params: set = None,
                 path: Union[str, Path] = None, ):
        """constructor"""

        super().__init__()

        name = convert2ascii(name)
        if name:
            self.name = name
        else:
            raise ValueError("Sequence name is invalid")

        self.params = set()
        self.path = path
        self.subject_id = None
        self.session_id = None
        self.run_id = None
        self.timestamp = None
        if isinstance(params, dict):
            self.params = set(list(params.keys()))
            self.__dict__.update(params)

        # parameters and their values can be modified
        self._mutable = True

    def get_session_info(self):
        """method to get metadata to the sequence"""
        return self.subject_id, self.session_id, self.run_id

    def add(self, param_list: Union[BaseParameter, Iterable[BaseParameter]]):
        """method to add new parameters; overwrite previous values if exists."""

        if not isinstance(param_list, Iterable):
            param_list = [param_list, ]

        for param in param_list:
            if not isinstance(param, BaseParameter):
                raise ValueError(
                    f'Input value {param} is not of type BaseParameter')

            # retaining full Parameter instance, not just value
            self.__dict__[param.name] = param
            self.params.add(param.name)

    def __setitem__(self,
                    key: str,
                    value: BaseParameter):
        """setter"""

        if not isinstance(value, BaseParameter):
            raise ValueError('Input value is not of type BaseParameter')

        if not isinstance(key, str):
            raise ValueError('Input name is not a string!')

        self.__dict__[key] = value
        self.params.add(key)

    def get(self, name, not_found_value=None):
        """getter"""
        return self.__getitem__(name=name, not_found_value=not_found_value)

    def __getitem__(self, name,
                    not_found_value=None):
        """getter"""

        try:
            return self.__dict__[name]
        except KeyError:
            if not_found_value is not None:
                return not_found_value
            else:
                raise KeyError(f'{name} has not been set yet')

    def compliant(self, other, rtol=0, decimals=None, include_params=None):
        """
        Method to check if one sequence is compatible w.r.t another,
        either in equality or within acceptable range, for each parameter.

        Parameters
        ----------
        other : BaseSequence
            The other sequence to compare with.
        rtol : float
            Relative tolerance. The relative difference is equal to
            ``rtol * abs(b)``. Default is 0.
        decimals : int
            Number of decimal places to consider for comparison. Default is 3.
        include_params : list
            The list of parameters to include while comparing two sequences. Default
            is all parameters.
        """

        # TODO: Split the method into compliant and diff
        #  to return differences between two sequences
        #  something similar to diff in bash

        if not isinstance(other, BaseSequence):
            raise TypeError(f'Sequence to compare {other} is not of type '
                            f'BaseSequence')

        if self.params != other.params:
            diff = self.params.symmetric_difference(other.params)
            # Don't raise error, just warn. It might be the case that
            # the two sequences are different. For example, if compliance
            # is checked only for a subset of parameters.
            logger.debug('different sets of parameters - '
                         'below params exist in one but not the other :\n\t{}'
                         ''.format(diff))
            # return False, diff  # TODO varying dtype: list of names!

        non_compliant_params = list()
        if include_params is None:
            include_params = self.params
        for pname in include_params:
            # if pname in other.params:
            try:
                this_param = self.__dict__[pname]
                that_param = other[pname]
            except KeyError:
                # If the parameter is not found in either of the sequences,
                #   skip it and move on to the next one. That means, the
                #   parameter is not required for compliance. And the parameter
                #   is not tagged as non-compliant.
                logger.info(f'{pname} not found in either of '
                            f'the sequences <{self, other}>')
                continue

            compliant = self._check_compliance(this_param, that_param, rtol=rtol, decimals=decimals)
            if not compliant:
                non_compliant_params.append((this_param, that_param))

        bool_flag = len(non_compliant_params) < 1

        return bool_flag, non_compliant_params  # list of BaseParameter classes

    def _check_compliance(self, this_param, that_param, rtol, decimals=None):
        if isinstance(this_param, NumericParameter) or \
                isinstance(this_param, MultiValueNumericParameter):
            compliant = this_param.compliant(that_param, rtol=rtol,
                                             decimals=decimals)
        else:
            compliant = this_param.compliant(that_param)
        return compliant

    def __eq__(self, other):
        """equivalence operator"""

        bool_flag, _ = self.compliant(other)
        return bool_flag

    def __delitem__(self, key):
        del self.__dict__[key]
        self.params.remove(key)

    def __iter__(self):
        return iter(self.params)

    def __len__(self):
        return len(self.params)

    def __str__(self):
        """human readable representation"""

        plist = list()
        for key in self.params:
            param = self.__dict__[key]
            name = param.acronym if param.acronym else param.name
            if not isinstance(param.get_value(), UnspecifiedType):
                plist.append(f'{name}={param.get_value()}')

        return '{}({})'.format(self.name, ','.join(plist))

    def __repr__(self):
        return self.__str__()


class BaseProtocol(ABC):
    """
    Base class for all protocols.

    A protocol is a sequence, except it is not mutable, to serve as a reference.

    Parameters
    ----------
    name : str
        Name of the protocol.
    """

    def __init__(self,
                 name="Protocol"):
        """constructor"""
        self._mutable = False
        self.name = convert2ascii(name)


class BaseImagingProtocol(BaseProtocol):
    """Base class for all imaging protocols such as MRI / neuroimaging.

    Parameters
    ----------
    name : str
        Name of the protocol.
    category : str
        Category of the protocol. For example, 'MR' for MRI, 'CT' for CT, etc.
        It should be one of the supported imaging modalities.
    """

    def __init__(self,
                 name='ImagingProtocol',
                 category='MR'):
        """constructor
        """

        super().__init__(name=name)

        # to distinguish between different types of imaging: MR, CT, XRAY etc.
        #   as they touch different portions of DICOM
        if category not in SUPPORTED_IMAGING_MODALITIES:
            raise TypeError(f'This modality {category} not supported.'
                            f'Choose one of {SUPPORTED_IMAGING_MODALITIES}')
        else:
            self._category = category
