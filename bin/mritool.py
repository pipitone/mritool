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
DRYRUN = False

def warn(message): 
    print "WARNING: {0}".format(message)

def verbose_message(message):
    if VERBOSE: log(message)

def log(message): 
    print "[{0}] {1}".format(datetime.datetime.now().isoformat(" "), message)

def copy_to_dir(path_from, path_to): 
    path_from = path_from.rstrip("/")
    if not os.path.isdir(path_to):
        raise Exception(
        "Cannot move {0} to {1} because destination is not a directory".format(
        path_from, path_to))

    command = "rsync -a {0} {1}/".format(path_from, path_to)
    verbose_message(command)

    if DRYRUN: return

    rtnval = os.system(command)
    if rtnval: 
        raise Exception("Error rsync'ing {0} to {1}/: return code {2}".format(
        path_from, path_to, rtnval))

        
def pull_exams(arguments): 
    examids    = arguments['<exam_number>']

    for line in os.popen("getallstudycodes"):     	
    
        (examid, studycode, date, patient_id, patient_name) = line.strip('\n').split('\t')

        if examids and examid not in examids:
            continue
        
        studydir    = staging_dir +"/" + studycode
        examdirname = "{studycode}_E{examid}_{date}_{patient_id}_{patient_name}" \
                        .format(**vars())
        examdir     = "{studydir}/{examdirname}".format(**vars())
        examinfo    = "{0}/{1}.info".format(studydir, examdirname)
        
        log("Considering exam {0} from study {1}...\n---".format(
            examid, studycode))

        os.path.isdir(studydir) or os.makedirs(studydir) 
        os.path.isdir(log_dir) or os.makedirs(log_dir) 
     
        
        # get dicoms
        if not os.path.isdir(examdir):  
            log("Fetching DICOMS into {0}".format(examdir))
            logfile = "{0}/{1}.getdicom.log".format(log_dir,examdirname)
            if os.system("getdicom -d {examdir} {examid} > {logfile}".format(
                **vars())):
                log("Error getting exam {0} DICOMS.".format(examid))
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
            #   - There is a matching dicom series with a single dicom image in
            #     it. 
            #   - The dicom image contains the following identifying attributes: 
            #         key = 0x0019109e, value == presssci
            #         key = 0x001910a2, value == pfile ID (e.g. P<pfileid>.7)
            #   - Action: Copy the single pfile to the series folder in staging
            #     and name the folder: E<examid>_spiral_<series_description>
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
            #   - Action: Move to a raw spiral backup directory
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
                copy_to_dir(pfile.path, examdir)
            elif kind == "fmri":
                parent_dir = os.path.dirname(pfile.path)
                verbose_message("Move {0} to {1}".format(parent_dir, examdir)) 
                copy_to_dir(parent_dir, examdir)
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
            
        
        log("Finished.\n---")


def package_exams(arguments): 
    # look in staging for <studycode>/.*E<examid>_.* folders

    for examid in arguments['<examid>']: 
        examdir_candidates = glob.glob(
            os.path.join(staging_dir,"*","*E{0}_*".format(examid)))
        if len(examdir_candidates) == 0: 
            warn("Unable to find exam {0} in the staging dir {1}. Skipping.".format(
                examid, staging_dir))
            continue
        if len(examdir_candidates) > 1: 
            warn("Found mulitple folders for exam {0} in staging dir {1}." 
                 "Skipping. {2}".format( examid, staging_dir, tuple(examdir_candidates)))
            continue


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
    mritool.py [options] pull [<exam_number>...]
    mritool.py [options] package <exam_number>...

Options: 
    --staging-dir=<dir>     Staging directory [default: {defaults[staging]}]
    --log-dir=<dir>         Logging directory [default: {defaults[logs]}]
    --pfile-dir=<dir>       Pfile directory [default: {defaults[raw]}]
    -n, --dry-run           Do nothing. 
    -v, --verbose           Verbose messaging.
""".format(defaults=defaults)

    arguments = docopt(options)
    staging_dir= arguments['--staging-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 

    DRYRUN = arguments['--dry-run']
    VERBOSE = arguments['--dry-run'] or arguments['--verbose']
    

    if arguments['pull']:
        pull_exams(arguments)
    if arguments['package']:
        package_exams(arguments)
