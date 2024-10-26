.. mrrc-hdr-qa documentation master file, created by
   sphinx-quickstart on Mon Oct 21 19:00:25 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

mrrc-hdr-qa documentation
=========================

Code to parse dicoms into a template database and alert on non-conforming sequences.

Code
--------

.. toctree::
   :caption: Contents:

.. autosummary::
   :toctree: _autosummary
   :recursive:

   dcmmeta2tsv
   acq2sqlite
   change_header


Overview
--------

See :py:data:`acq2sqlite.DBQuery.CONSTS`

.. image:: ../sphinx/imgs/nonconforming_example.png



.. `https://dicom-parser.readthedocs.io/en/latest/siemens/csa_headers.html#csa-headers`_


Parameters
----------

 .. csv-table:: Dicom tag list
    :file: ../taglist.txt
    :delimiter: \t
    :header-rows: 1

.. .. include:: ../readme.md
