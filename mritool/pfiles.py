# vim: expandtab ts=4 sw=4 tw=80: 

import os
import os.path
import dicom
import pfile_tools
import pfile_tools.headers
import pfile_tools.struct_utils
import sys

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
