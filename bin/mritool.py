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
import re

DICOM_PRESSCI_KEY = 0x0019109e
DICOM_PFILEID_KEY = 0x001910a2
VERBOSE = False

def warn(message): 
    print "WARNING: {0}".format(message)

def verbose_message(message):
    if VERBOSE: print message

def pull_exams(arguments): 
    staging_dir= arguments['--staging-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 
    dry_run    = arguments['--dry-run']
    examids    = arguments['<examid>']

    for line in os.popen("getallstudycodes"):     	
    
        (examid, studycode, date, patient_id, patient_name) = line.strip('\n').split('\t')

        if examids and examid not in examids:
            continue
        
        studydir    = staging_dir +"/" + studycode
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

        # merge in any pfiles from raw
        pfiles = mritools.get_all_pfiles_info(pfile_dir)
        for pfile in [p for p in pfiles.values() if str(p.headers['exam_number']) == examid]: 
            if ".bak" in pfile.path: continue 

            foldername = os.path.basename(os.path.dirname(pfile.path))
            # Use the following Heuristic to decide what to do with the pfiles
            #
            # There are several kinds of runs represented by pfiles, and they
            # can be identified and dealt with in the following ways.
            #
            # 1. Spectroscopy 
            #   - The series_description contains "MRS" (MR Spectroscopy)
            #   - There is a matching dicom series with a single dicom image in
            #     it. 
            #   - The dicom image contains the following identifying attributes: 
            #         key = 0x0019109e, value == presssci
            #         key = 0x001910a2, value == pfile ID (e.g. P<pfileid>.7)
            #   - Action: Copy the single pfile to the series folder in staging
            #
            # 2. HOS
            #   - The series_description is "HOS"
            #   - Action: Ignore
            #
            # 3. fMRI 
            #   - They are stored in a folder named fMRI_P<pfileid>
            #   - Action: Copy the parent folder, and all it contains, to exam in staging
            #
            # 4. Raw spiral files
            #   - They are stored in a folder named rawSprlioPfiles
            #   - Action: Ignore
            kind = pfile.guess_kind()

            if kind == "spectroscopy":   
                # find series directory should be named ".*S0*<series>"
                n = pfile.headers["series_number"]
                series_dir = [d for d in os.listdir(examdir) if 
                    re.search(".*S0*{0}".format(n), d)]
                if len(series_dir) != 1: 
                    warn("Couldn't find folder for series {0} in exam dir {1} "
                         "for pfile {2}. Skipping.".format(n,examdir,pfile.path))
                    continue

                series_dir = os.path.join(examdir,series_dir[0])
                verbose_message("Move {0} to {1}".format(pfile.path, series_dir))
            elif kind == "fmri":
                parent_dir = os.path.dirname(pfile.path)
                verbose_message("Move {0} to {1}".format(parent_dir, examdir)) 
            elif kind == "hos" or kind == "raw": 
                verbose_message(
                    "Ignoring pfile {0} because it is type == {1}".format(
                    pfile.path, kind))
                continue 
            else: 
                warn("Unknown pfile kind {0}. Skipping.".format(pfile.path))
                
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
    --staging-dir=<dir>     Staging directory [default: {defaults[staging]}]
    --log-dir=<dir>         Logging directory [default: {defaults[logs]}]
    --pfile-dir=<dir>       Pfile directory [default: {defaults[raw]}]
    -n, --dry-run           Do nothing. 
    -v, --verbose           Verbose messaging.
""".format(defaults=defaults)

    arguments = docopt(options)
    VERBOSE = arguments['--dry-run'] or arguments['--verbose']
    pull_exams(arguments)
