# vim: expandtab ts=4 sw=4 tw=80: 

import os
import os.path
import dicom
import pfile_tools
from pfile_tools import headers, struct_utils
import sys

default_pfile_headers = [ 
    'exam_number',
    'exam_description', 
    'exam_type',
    'series_number', 
    'series_description', 
 ]

def get_pfile_info(path): 
    """Returns a dictionary of header->values for a pfile.

Returns None if the specified path does not point to valid pfile."""

    pfile_headers = default_pfile_headers
    try: 
        ph = pfile_tools.headers.Pfile.from_file(path)
        dump = struct_utils.dump_struct(ph.header)
        info = {}
        for record in dump: 
            if record.label in pfile_headers:
                info[record.label] = record.value
        return info
    except (IOError, headers.UnknownRevision): 
        return None

def get_all_pfiles_info(root): 
    """Traverses a directory looking for pfiles. 

Returns a dictionary mapping the path of a pfile to attributes about the pfile.
"""
    infos = {}
    for (path, dirs, files) in os.walk(root):
        for f in files: 
            full_path = os.path.join(path, f)
            info = get_pfile_info(full_path)
            if info: infos[full_path] = info
    return infos
