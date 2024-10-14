#!/usr/bin/env python3
import os
from pathlib import Path
import logging
import pydicom
from collections import Counter
from email.mime.text import MIMEText
import smtplib


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
    for root, dirs, files in os.walk(data_source):
        for file in files:
            if file.endswith(".dcm"):
                dicom_path = os.path.join(root, file)
                try:
                    # Load the DICOM file using pydicom
                    dicom_data = pydicom.dcmread(dicom_path)

                    # Pull the metadata
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

# Import the config from the json file
def get_config(config_path):
    import json
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config

def infer_protocol(dataset, config):
    """
    Infers the reference protocol by determining the most common
    values for important DICOM fields (e.g., SliceThickness, EchoTime).

    Parameters
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

    # Group sequences by the stratify_by parameters, if specified
    sequences_by_group = {}

    for seq in dataset["sequences"]:
        dicom_metadata = seq["metadata"]

        # Determine the group to stratify by (e.g., series number) if needed
        if stratify_by and hasattr(dicom_metadata, stratify_by):
            group_value = getattr(dicom_metadata, stratify_by)
        else:
            group_value = "default_group"  # Single group if no stratify_by

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
                most_common_value = param_counter.most_common(1)[0][0]
                group_reference[param] = most_common_value
            else:
                group_reference[param] = None  # If no value is found for the parameter

        # Add the inferred protocol for this group to the reference protocol
        reference_protocol[group] = group_reference
        
    return reference_protocol

def horizontal_audit(dataset, config_path):
    """
    Perform the horizontal audit on the dataset using the sequences extracted
    from DICOM files. The audit checks if sequences are compliant with
    an inferred protocol.

    Parameters
    ----------
    dataset : dict
        Dataset containing DICOM sequences and metadata.
    config_path : str
        Path to the configuration file.
    
    Returns
    -------
    results : dict
        A dictionary with compliant, non-compliant sequences, and the 
        inferred reference protocol.
    """
    # Load the configuration file to determine the parameters for compliance
    config = get_config(config_path)
    
    # Extract the configuration for horizontal audits
    horizontal_audit_config = config.get("horizontal_audit", {})
    
    # List of parameters to include in the compliance check
    include_params = horizontal_audit_config.get("include_parameters", [])
    
    # Parameter used to group sequences, such as 'series_number'
    stratify_by = horizontal_audit_config.get("stratify_by", None)
    
    # Infer the reference protocol from the dataset
    reference_protocol = infer_protocol(dataset, config)
    
    # Tolerance configuration: allows parameter-specific tolerances
    tolerance_config = config.get("tolerance", {})

    # Lists to hold compliant and non-compliant sequences
    compliant_ds = []
    non_compliant_ds = []
    
    # Group sequences by the value of the 'stratify_by' parameter
    sequences_by_group = {}

    # Loop through each sequence in the dataset
    for seq in dataset['sequences']:
        dicom_metadata = seq['metadata']
        
        # Determine the group for this sequence based on the 'stratify_by' parameter
        group_value = getattr(dicom_metadata, stratify_by, "default_group")
        
        # Initialize the group if it doesn't already exist
        if group_value not in sequences_by_group:
            sequences_by_group[group_value] = []
        
        # Add the sequence to its corresponding group
        sequences_by_group[group_value].append(seq)

    # Now, audit each group of sequences separately
    for group, sequences in sequences_by_group.items():
        # Loop through each sequence within the group
        for seq in sequences:
            dicom_metadata = seq['metadata']
            is_compliant = True
            non_compliant_reasons = []

            # Compare each included parameter against the reference protocol
            for param in include_params:
                # Get the reference value for the parameter from the reference protocol
                ref_value = reference_protocol[group].get(param)
                
                # Fetch the parameter-specific tolerance from the config (default: 0.1)
                tolerance = tolerance_config.get(param, 0.1)

                # Check if the parameter exists in the DICOM metadata
                if hasattr(dicom_metadata, param):
                    seq_value = getattr(dicom_metadata, param)

                    # If the parameter is numeric, allow some tolerance in comparison
                    if isinstance(ref_value, (int, float)) and isinstance(seq_value, (int, float)):
                        # Check if the value exceeds the allowed tolerance
                        if abs(ref_value - seq_value) > tolerance:
                            is_compliant = False
                            non_compliant_reasons.append(f"{param}: {seq_value} (Expected: {ref_value}, Tolerance: {tolerance})")
                    
                    # If the parameter is non-numeric, check for an exact match
                    elif ref_value != seq_value:
                        is_compliant = False
                        non_compliant_reasons.append(f"{param}: {seq_value} (Expected: {ref_value})")

            # If the sequence is compliant, add it to the compliant dataset
            if is_compliant:
                compliant_ds.append(seq)
            else:
                # If the sequence is not compliant, add reasons and log it
                seq['non_compliant_reasons'] = non_compliant_reasons
                non_compliant_ds.append(seq)

    # Return the results of the audit, including compliant and non-compliant sequences
    return {
        'compliant': compliant_ds,
        'non_compliant': non_compliant_ds,
        'reference': reference_protocol
    }


# Check if a scan has been processed
def is_scan_processed(log_file, scan_date):
    if os.path.exists(log_file):
        with open(log_file, "r") as log:
            processed_scans = log.readlines()
            return scan_date in [line.strip() for line in processed_scans]
    return False

# Log a processed scan
def log_processed_scan(log_file, scan_date):
    with open(log_file, "a") as log:
        log.write(f"{scan_date}\n")

def send_email_alert(subject, message, config):
    """
    Send an email alert using the provided email configuration.

    Parameters:
    -----------
    subject : str
        The subject of the email.
    message : str
        The body of the email.
    config : dict
        A dictionary containing the email settings, including SMTP server details.
    """
    email_settings = config.get("email_settings", {})
    from_email = email_settings.get("from", "default@domain.com")
    to_email = email_settings.get("to", ["default@domain.com"])
    smtp_server = email_settings.get("smtp_server", "localhost")
    smtp_port = email_settings.get("smtp_port", 25)
    use_tls = email_settings.get("use_tls", False)

    # Get the email password from environment variable (ensure you've set this up)
    email_password = os.getenv("EMAIL_PASSWORD")

    # Create the email message
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_email)

    # Connect to the SMTP server and send the email
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if use_tls:
                server.starttls()  # Upgrade to TLS if necessary
            server.login(from_email, email_password)
            server.send_message(msg)
        print(f"Email sent successfully to {', '.join(to_email)}")
    except Exception as e:
        print(f"Failed to send email: {e}")

# Process individual scans
def process_scan(scan_dir, config_path, output_dir):
    try:
        config = get_config(config_path)
        exclude_subjects = config.get("exclude_subjects", [])

        # Check if the subject is in the exlusion list
        subject_id = Path(scan_dir).name
        if subject_id in exclude_subjects:
            logging.info(f"Skipping excluded subject: {subject_id}")
            return # Skip this scan
        
        # Import dataset
        dataset = import_dataset_from_dicom(data_source=scan_dir, ds_format="dicom", config_path=config_path)

        # Perform horizontal audit
        hz_audit_results = horizontal_audit(dataset=dataset, config_path=config_path)

        # If non-compliant, send an email alert
        if hz_audit_results['non_compliant']:
            subject = f"Non-compliant Scan Detected - {Path(scan_dir).name}"
            message = f"Non-compliant scans foudn in {Path(scan_dir)}. Review the report"
            logging.warning(f"Non-compliant scan detected in {scan_dir}")
            send_email_alert(subject, message)

        logging.info(f"Scan {Path(scan_dir)} processed successfully.")
    except Exception as e:
        logging.error(f"Failed to process scan {scan_dir}: {e}")

# Main function
def main():

    # Grab the paths
    SCAN_DIRECTORY = "/Volumes/Hera/Raw/MRprojects/Habit/"
    filedir = Path(os.path.dirname(__file__))
    LOG_FILE_PATH = filedir / "log_file.txt"
    CONFIG_PATH = filedir / "mri-config.json"
    OUTPUT_DIR = filedir / "output.txt"
    # TODO: use argparser to grab theses settings from command line

    # Iterate through scans in the specified directory
    for scan_dir in Path(SCAN_DIRECTORY).glob("*/"):
        scan_date = scan_dir.name

        # Check if scan is already processed
        if is_scan_processed(LOG_FILE_PATH, scan_date):
            logging.info(f"Skipping already processed scan: {scan_date}")
            continue

        # Process the scan
        logging.info(f"Processing scan: {scan_date}")
        process_scan(scan_dir, CONFIG_PATH, OUTPUT_DIR)

        # Log the processed scan
        log_processed_scan(LOG_FILE_PATH, scan_date)
    
if __name__ == "__main__":
    main()
