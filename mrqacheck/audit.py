import os
from pathlib import Path
import logging
import pydicom
from collections import Counter

# Grab the paths
SCAN_DIRECTORY = "/Volumes/Hera/Raw/MRprojects/Habit/"
LOG_FILE = "/home/hudlowe/src/mrrc-hdr-qa/mrqacheck/log_file.txt"
CONFIG_PATH = "/home/hudlowe/src/mrrc-hdr-qa/mrqacheck/mri-config.json"
OUTPUT_DIR = "/home/hudlowe/src/mrrc-hdr-qa/mrqacheck/output.txt"
EMAIL_RECIPIENT = "hudlowe@upmc.edu"

data_source = "/Volumes/Hera/Raw/MRprojects/Habit/"

# Open the logger
logging.basicConfig(filename="audit_script.log", level=logging.INFO)

def import_dataset_from_dicom(data_source, ds_format="dicom", config_path=None):
    """
    Import DICOM dataset using pydicom. This will scan the provided data source
    for DICOM files, read them, and organize them.

    Parameters
    ----------
    data_source : str or Path
        The directory containing the DICOM files.
    ds_format : str
        Format of the dataset.
    config_path : str
        Path to the configuration file

    Returns
    -------
    dataset : dict
        A dictionary representing the dataset with metadata extracted from DICOM files.
    """

    dataset = {"name": Path(data_source).name, "sequences": []}

    # Loop through the data_source directory
    for root, files in os.walk(data_source):
        for file in files:
            if file.endswitch(".dcm"):
                dicom_path = os.path.join(root, file)
                try:
                    # Load the DICOM file using pydicom
                    dicom_data = pydicom.dcmread(dicom_path)

                    # PUll the metadata
                    sequence_name = dicom_data.SeriesDescription if 'SeriesDescription' in dicom_data else "UnknownSequence"

                    # Add to the dataset
                    dataset["sequences"].append({
                        "file": dicom_path,
                        "sequence_name": sequence_name,
                        "metadata": dicom_data
                    })
                except Exception as e:
                    print(f"Error reading DICOM file {file}: {e}")
    return dataset

dataset = import_dataset_from_dicom(data_source)

# Imoprt the config from the json file
def get_config(config_path):
    import json
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config

def infer_protocol(dataset, config):
    """
    Infers the reference protocol by detereming the most common
    values for important DICOM fields (e.g. SliceThickness, EchoTime).

    Paramaters
    ----------
    dataset : dict
        The dataset containing DICOM sequences with metadata.
    config : dict
        Configuration file specifying the parameters to include in the
        reference protocol.
    
    Returns
    -------
    reference_protocol : dict
        A dictionary representing the reference protocol, where the most
        common values for each important parameter are stored.
    """
    # Extract horizontal audit parameters from the config
    horizontal_audit_config = config.get("horizontal_audit", {})
    include_params = horizontal_audit_config.get("include_parameters", [])
    stratify_by = horizontal_audit_config.get("stratify_by", None)

    # Initialize a dictionary to hold the counts of each parameter's values
    param_counters = {param: Counter() for param in include_params}

    # Gruop sequences by the stratify_by parameters, if specified 
    sequences_by_group = {}

    for seq in dataset["sequences"]:
        dicom_metadata = seq["metadata"]

        # Deteremine the group to stratify by (e.g., series number) if needed
        if stratify_by and hasattr(dicom_metadata, stratify_by):
            group_value = getattr(dicom_metadata, stratify_by)
        else:
            group_value = "default_group" # Single group if no stratisfy_by

        # Initialize the group if not already present
        if group_value not in sequences_by_group:
            sequences_by_group[group_value] = []

        sequences_by_group[group_value].append(dicom_metadata)

    # Infer protocol for each group
    reference_protocol = {}

    for group, sequences in sequences_by_group.items():
        group_reference = {}

        # For each parameter, count the occurrence of its values across all sequences
        for param in include_params:
            param_counter = Counter()
            for dicom_metadata in sequences:
                if hasattr(dicom_metadata, param):
                    value = getattr(dicom_metadata, param)
                    param_counter[value] += 1

            # Get the most common value for the parameter in this group
            if param_counter:
                most_common_value = param_counter.most_common[1][0][0]
                group_reference[param] = most_common_value
            else:
                group_reference[param] = None # If no value is found for the paramater

        # Add the inferred protocol for this group to the reference protocol
        reference_protocol[group] = group_reference
        
    return reference_protocol



def horizontal_audit(dataset, config_path, tolerance=0.1):
    """
    Perform the horizontal audit on the dataset using the sequences extracted
    from DICOM files. The audit checks if sequences are compliant with
    a reference protocol.

    Parameters
    ----------
    dataset : dict
        Dataset containing DICOM sequences and metadata
    config_path : str
        Path to the configuration file.
    tolerance : float
        The tolerance level for compliance checks (default is 0.1).

    Returns
    -------
    results : dict
        A dictionary with compliant, non-compliant sequenes, and the 
        reference protocol.
    """
    # Load the configuartion to determine paramaters for compliance
    config = get_config(config_path)
    horizontal_audit_config = config.get("horizontal_audit", {})
    include_params = horizontal_audit_config.get("indlude_parameters", [])

    # Infer or load a reference protocol for compliance checks
    reference_protocol = infer_protocol(dataset, config)

    # Create placeholder lists for the compliant and non_compliant sequences
    compliant_ds = []
    non_compliant_ds = []

    # Loop through each sequence in the dataset
    for seq in dataset['sequences']:
        dicom_metadata = seq['metadata']
        is_compliant = True
        non_compliant_reasons = []

        # Compare each included parameter against the reference protocol
        for param in include_params:
            ref_valeu = reference_protocol.get(param)

            # Check if the parameter exists in the DICOM metadata
            if hasattr(dicom_metadata, param):
                seq_value = getattr(dicom_metadata, param)

