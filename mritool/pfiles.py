# vim: expandtab ts=4 sw=4 tw=80: 

import os
import os.path
import dicom
import pfile_tools
import pfile_tools.headers
import pfile_tools.struct_utils
import sys

def guess_pfile_kind(path, headers): 
    # Use the following Heuristic to decide what to do with the pfiles
    #
    # There are several kinds of runs represented by pfiles, and they
    # can be identified (rather inelegantly) in the following ways.
    #
    # 1. Spectroscopy 
    #   - The series_description contains "MRS" (MR Spectroscopy)
    #   - There is a matching dicom series with a single dicom image in
    #     it. 
    #   - The dicom image contains the following identifying attributes: 
    #         key = 0x0019109e, value == presssci
    #         key = 0x001910a2, value == pfile ID (e.g. P<pfileid>.7)
    #
    # 2. HOS
    #   - The series_description is "HOS"
    #
    # 3. fMRI 
    #   - They are stored in a folder named fMRI_P<pfileid>
    #
    # 4. Raw spiral files
    #   - They are stored in a folder named rawSprlioPfiles
    series_description = headers["series_description"]
    foldername = os.path.basename(os.path.dirname(path))

    if series_description.startswith("MRS"): 
        return "spectroscopy"
    elif series_description == "HOS":
        return "hos"
    elif foldername.startswith("fMRI_P"):
        return "fmri"
    elif foldername.startswith("rawSprlioPfiles"):
        return "raw"
    else: 
        return "unknown"

def get_pfile_headers(path): 
    """
    Returns a dictionary of header->values for a pfile.

    Returns None if the specified path does not point to valid pfile.
    """

    try: 
        ph = pfile_tools.headers.Pfile.from_file(path)
        dump = pfile_tools.struct_utils.dump_struct(ph.header)
        headers = { record.label: record.value for record in dump }
        return headers
    except (IOError, pfile_tools.headers.UnknownRevision): 
        return None

def get_all_pfiles_headers(root): 
    """
    Traverses a directory looking for pfiles. 

    Returns a dictionary mapping the path of a pfile to a dict of attributes about the pfile.
    """
    pfiles = {}
    for (path, dirs, files) in os.walk(root, followlinks=True):
        for f in files: 
            full_path = os.path.join(path, f)
            headers = get_pfile_headers(full_path)
            if headers: 
                pfiles[full_path] = headers
    return pfiles
