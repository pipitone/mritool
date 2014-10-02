#!/bin/env python
# vim: expandtab ts=4 sw=4 tw=80: 
from mritools import mritools 
from docopt import docopt
import os
import stat
import pwd
import grp
import os.path
import datetime 
import dicom
import glob 
import sys
import UserDict
import re
import traceback 

DICOM_PRESSCI_KEY = 0x0019109e
DICOM_PFILEID_KEY = 0x001910a2
VERBOSE = False
DRYRUN = False

def fatal(message, exception = None): 
    print "FATAL: {0}".format(message)
    if exception: 
        print traceback.print_exc(exception)
    sys.exit(1)

def warn(message): 
    print "WARNING: {0}".format(message)

def verbose_message(message):
    if VERBOSE: log(message)

def log(message): 
    print "{0}".format(message)

def run(command): 
    verbose_message("EXEC: " + command)
    if DRYRUN: return 
    os.system(command)

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
    scans_dir  = arguments['--scans-dir']
    staging_dir= arguments['--staging-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 

    for line in os.popen("getallstudycodes"):     	
    
        (examid, studycode, date, patient_id, patient_name) = line.strip('\n').split('\t')

        # Study codes can appear with ammendment markers in their names
        # indicating that the scan was somehow modified. This shows up as 'e+1'
        # appended to the study code name, e.g. for an ammended scan with study
        # code 'SPINS1MR', it appears in the dicom headers as 'e+1 SPINS1MR'. 
        #
        # For naming, we'll just ignore the ammendment markers entirely. 
        studycode = studycode.split(" ")[-1] # ignore up to after last space

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
        if os.path.isdir(examdir):  
            verbose_message(
                "Exam {0} folder exists {1}. Skip fetching DICOMS.".format(examid, examdir)) 
        else:
            log("Fetching DICOMS into {0}".format(examdir))
            logfile = "{0}/{1}.getdicom.log".format(log_dir,examdirname)
            if run("getdicom -d '{examdir}' {examid} > {logfile}".format(
                **vars())):
                log("Error getting exam {0} DICOMS.".format(examid))
                continue
            run("examinfo {0} | tee {1} > {2}/exam_info.txt".format(
                examid, examinfo, examdir))
            run("listseries11 {0} | tee -a {1} > {2}/exam_info.txt".format(
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
                verbose_message("Found pfile {0} to for series {1}".format(pfile.path, n))
                copy_to_dir(pfile.path, examdir)
            elif kind == "fmri":
                parent_dir = os.path.dirname(pfile.path)
                verbose_message("Found fMRI scan {0}".format(parent_dir)) 
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

                pfiles = glob.glob(series_dir + "/"+str(pfile_id)+".7")  
                if len(pfiles) == 0: 
                    warn(
                        "Exam {0}/Series {1} needs a pfile (id: {2}) but none was found in {1}.".format(
                            examid,series_dir,pfile_id))
        log("Finished.\n---")


def package_exams(arguments): 
    scans_dir  = arguments['--scans-dir']
    staging_dir= arguments['--staging-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 

    # look in staging for <studycode>/.*E<examid>_.* folders
    for examid in arguments['<exam_number>']: 
        examdir_candidates = glob.glob(
            os.path.join(staging_dir,"*","*E{0}_*".format(examid)))

        examdir_candidates = [x for x in examdir_candidates if os.path.isdir(x) ]
        if len(examdir_candidates) == 0: 
            warn("Unable to find exam {0} in the staging dir {1}. Skipping.".format(
                examid, staging_dir))
            continue
        if len(examdir_candidates) > 1: 
            warn("Found mulitple folders for exam {0} in staging dir {1}." 
                 "Skipping. {2}".format( examid, staging_dir, tuple(examdir_candidates)))
            continue

        exam_path = examdir_candidates[0]
        exam_name = os.path.basename(exam_path)
        study_code = os.path.basename(os.path.dirname(exam_path))

        study_dir = "{0}/{1}".format(scans_dir,study_code)
        pkg_path  = "{0}/{1}.tar.gz".format(study_dir,exam_name)
        info_path = "{0}/{1}.info".format(study_dir,exam_name)
        
        if os.path.exists(pkg_path) and not arguments['--force']: 
            warn("{0} package already exists. Skipping. Use --force to overwrite.".format(
                pkg_path))
        else: 
            log("Packing exam {0} as {1}".format(examid, pkg_path))
            if not os.path.exists(study_dir): 
                fatal("Study folder {0} does not exist.".format(
                    study_dir))
                continue
            run("tar czf {0} {1}*".format(pkg_path,exam_path))
            run("cp {0}.info {1}".format(exam_path,info_path))

        log("Setting permissions to be group ({0}) readable only.".format(study_code))
        try: 
            study_code_group_id = grp.getgrnam(study_code).gr_gid
            print study_code_group_id
            if not DRYRUN:
                os.chown(pkg_path, -1, study_code_group_id)
                os.chown(info_path, -1, study_code_group_id)
                os.lchmod(pkg_path, 0640)
                os.lchmod(info_path, 0640)
        except (KeyError, OSError) as e:
            fatal("Unable to set permissions ({0}) {1}".format(e.errno, e.strerror), e)
            
def main(): 
    global DRYRUN 
    global VERBOSE

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
    --scans-dir=<dir>       Staging directory [default: {defaults[scans]}]
    --staging-dir=<dir>     Staging directory [default: {defaults[staging]}]
    --log-dir=<dir>         Logging directory [default: {defaults[logs]}]
    --pfile-dir=<dir>       Pfile directory [default: {defaults[raw]}]
    -f, --force             Force, overwrite files if needed.
    -n, --dry-run           Do nothing, but show what would be done. 
    -v, --verbose           Verbose messaging.
""".format(defaults=defaults)

    arguments = docopt(options)

    DRYRUN = arguments['--dry-run']
    VERBOSE = arguments['--verbose']
    
    if arguments['pull']:
        pull_exams(arguments)
    if arguments['package']:
        package_exams(arguments)
    
if __name__ == "__main__":
    main()
