#!/bin/env python
# vim: expandtab ts=4 sw=4 tw=80: 
from mritools import mritools 
from docopt import docopt
import os
import os.path
import datetime 
import dicom
import glob 
import sys
import UserDict

DICOM_PRESSCI_KEY = 0x0019109e
DICOM_PFILEID_KEY = 0x001910a2

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




if __name__ == "__main__":
    defaults = UserDict.UserDict()
    defaults['mrraw']   = os.environ.get("MRRAW_DIR"  ,"./output/mrraw")
    defaults['raw']     = os.environ.get("RAW_DIR"    ,"./output/raw")
    defaults['staging'] = os.environ.get("STAGING_DIR","./output/staging")
    defaults['scans']   = os.environ.get("SCANS_DIR"  ,"./output/scans")
    defaults['logs']    = os.environ.get("LOGS_DIR"   ,"./output/logs")
    options = """ 
Finds and copies exam data into a well-organized folder structure.

Usage: 
    mritool.py [options] [pull] [<examid>...]
Options: 
    -n, --dry-run           Do nothing. 
    --output-dir=<dir>      Output directory [default: {defaults[staging]}]
    --log-dir=<dir>         Logging directory [default: {defaults[logs]}]
    --pfile-dir=<dir>       Pfile directory [default: {defaults[raw]}]
""".format(defaults=defaults)
    arguments = docopt(options)
    pull_exams(arguments)

