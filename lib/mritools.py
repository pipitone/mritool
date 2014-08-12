# vim: expandtab ts=4 sw=4 tw=80: 

import os
import os.path
import datetime 
import dicom
import pfile_tools
from pfile_tools import headers, struct_utils
import glob 
import sys

DICOM_PRESSCI_KEY = 0x0019109e
DICOM_PFILEID_KEY = 0x001910a2
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

def pull_exams(arguments): 
    output_dir = arguments['--output-dir']
    log_dir    = arguments['--log-dir'] 
    dry_run    = arguments['--dry-run']
    examids    = arguments['<examid>']

    for line in os.popen("getallstudycodes"):     	
    
        (examid, studycode, date, patient_id, patient_name) = line.strip('\n').split('\t')

        if examids and examid not in examids:
            continue
        
        studydir    = output_dir +"/" + studycode
        examdirname = "{studycode}_E{examid}_{date}_{patient_id}_{patient_name}" \
                        .format(**vars())
        examdir     = "{studydir}/{examdirname}".format(**vars())
        examinfo    = "{0}/{1}.info".format(studydir, examdirname)
        
        print "Considering exam {0} from study {1}... ".format(
            examid, studycode),

        os.path.isdir(studydir) or os.makedirs(studydir) 
        os.path.isdir(log_dir) or os.makedirs(log_dir) 
     
        print "checking.\n---" 
        
        # get dicoms
        if not os.path.isdir(examdir):  
            print "Fetching DICOMS into {0}".format(examdir)
            logfile = "{0}/{1}.getdicom.log".format(log_dir,examdirname)
            if os.system("getdicom -d {examdir} {examid} > {logfile}".format(
                **vars())):
                print "Error getting exam {0} DICOMS.".format(examid)
                continue
            os.system("examinfo {0} | tee {1} > {2}/exam_info.txt".format(
                examid, examinfo, examdir))
            os.system("listseries11 {0} | tee -a {1} > {2}/exam_info.txt".format(
                examid, examinfo, examdir))

        # get pfiles
        for series_dir in glob.glob(examdir + "/E*"): 
            for dcm_file in glob.glob(series_dir +"/*.dcm"): 
                ds = dicom.read_file(dcm_file)

                if DICOM_PRESSCI_KEY not in ds or ds[DICOM_PRESSCI_KEY].value != "presscsi": 
                    break 

                if DICOM_PFILEID_KEY not in ds: 
                    print "Error.. pfile field not found"
                    break 

                pfile_id = ds[DICOM_PFILEID_KEY].value
                print "TODO: fetch pfile", pfile_id, "for series", series_dir
                break
            
        
        print "[{0}] Finished. ".format(datetime.datetime.now().isoformat(" "))
        print "---\n"

