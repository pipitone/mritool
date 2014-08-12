# vim: expandtab ts=4 sw=4 tw=80: 

import os
import os.path
import dicom
import pfile_tools
from pfile_tools import headers, struct_utils
import sys

class PFile: 
    def __init__(self, path): 
        self.path = path
        self.headers = {}
        

def get_pfile_info(path): 
    """Returns a dictionary of header->values for a pfile.

Returns None if the specified path does not point to valid pfile."""

    try: 
        ph = pfile_tools.headers.Pfile.from_file(path)
        dump = struct_utils.dump_struct(ph.header)
        pfile = PFile(path)
        for record in dump: 
            pfile.headers[record.label] = record.value
        return pfile 
    except (IOError, headers.UnknownRevision): 
        return None

def get_all_pfiles_info(root): 
    """Traverses a directory looking for pfiles. 

Returns a dictionary mapping the path of a pfile to attributes about the pfile.
"""
    pfiles = {}
    for (path, dirs, files) in os.walk(root):
        for f in files: 
            full_path = os.path.join(path, f)
            pfile = get_pfile_info(full_path)
            if pfile: pfiles[full_path] = pfile 
    return pfiles
