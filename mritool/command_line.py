#!/bin/env python
# vim: expandtab ts=4 sw=4 tw=80: 
import pfiles
import scu
from docopt import docopt
import shutil
import datetime
import tabulate
import tempfile
import logging
import os
import pwd
import os.path
import fnmatch
import dicom
import glob 
import sys
import UserDict
import re
import traceback 
import subprocess
import shlex
from collections import defaultdict

VERBOSE = False
DEBUG   = False
MIN_SERVICE_EXAM_NUM = 50000   # exam/StudyID greater than this are GE service
                               # exams, and they should be ignored during sync.
                               # See https://github.com/TIGRLab/mritool/issues/31
DICOM_PRESSCI_KEY = 0x0019109e
DICOM_PFILEID_KEY = 0x001910a2
EXAMID_PADDING = 5      # Zero pad chars when formatting exam IDs
SERIESNUM_PADDING = 5   # Zero pad chars when formatting exam series numbers 
INSTANCE_PADDING = 5    # Zero pad chars when formatting dicom instance numbers

####
#  Logging
###########################################
logging.basicConfig(format='%(message)s')
logger = logging.getLogger('mritool')

def fatal(message, exception = None): 
    logger.critical("FATAL: {}".format(message))
    if exception: 
        logging.critical(traceback.print_exc(exception))
    sys.exit(1)

def warn(message): 
    logger.warning("WARNING: {0}".format(message))

def debug(message):
    logger.debug(message)

def verbose(message):
    if DEBUG or VERBOSE: log(message)

def log(message): 
    logger.info(message)

####
#  Formatting functions
###########################################
def mangle(text): 
    """
    Mangles text to make it suitable for file names
    """
    return re.sub(r'[\W_]+','-',text)

def format_exam_name(examinfo):
    """
    Returns a well-formatted exam folder name. 

    Expects a dictionary of info about the exam as would be returned by findscu. 
    """ 

    # Booking codes can appear with ammendment markers 'e+1' in their names
    # indicating that the scan was somehow modified.
    ammendment = "" 
    bookingcode  = examinfo.get("StudyDescription","UNKNOWN")    # by default this is the booking code
    if bookingcode.split(" ")[0].startswith("e+"):  
        ammendment   = bookingcode.split(" ")[0]
        bookingcode  = " ".join(bookingcode.split(" ")[1:])

    return "{date}_Ex{examid}_{bookingcode}_{patientid}{ammendment}".format(
              date        = examinfo.get("StudyDate", "UNKNOWN"),
              examid      = examinfo.get("StudyID").zfill(EXAMID_PADDING),
              bookingcode = mangle(bookingcode),
              patientid   = mangle(examinfo.get("PatientID","UNKNOWN")), 
              ammendment  = re.sub(r'\W','', ammendment))

def format_series_name(examid, series, seriesdescr):
    """
    Returns a well formatted series folder name.
    """
    return "Ex{examid}_Se{series}_{descr}".format(
              examid = str(examid).zfill(EXAMID_PADDING),
              series = str(series).zfill(SERIESNUM_PADDING),
              descr  = mangle(seriesdescr)) 

def format_dicom_name(examid, series, instance):
    """
    Returns a well-formatted dicom file name.
    """ 

    return "Ex{examid}Se{series}Im{instance}.dcm".format(
              examid   = examid.zfill(EXAMID_PADDING),
              series   = seq.zfill(SERIESNUM_PADDING),
              instance = instance.zfill(INSTANCE_PADDING))

####
# Helper functions
###########################################

def listdir_fullpath(d):
    """
    Returns the full path for subdirectories of d
    """
    return [os.path.join(d, f) for f in os.listdir(d)]

def index_dicoms(path, recurse = True, maxdepth = -1, complete = False): 
    """
    Generate a dictionary of files and their dicom headers.

    <path>      a path to the root folder
    <recurse>   a boolean, if true then will search subfolders recursively
    <maxdepth>  integer, depth to recurse to. -1 = no max depth
    <complete>  boolean, if false only a single dicom file per folder is indexed
    """

    manifest = {}

    # for each dir, we want to inspect files inside of it until we find a dicom
    # file that has header information
    for filepath in listdir_fullpath(path):
        try:
            if os.path.isdir(filepath): continue
            manifest[filepath] = dicom.read_file(filepath)
            if not complete: break
        except dicom.filereader.InvalidDicomError, e:
            pass

    if recurse and (maxdepth < 0 or maxdepth > 0): 
        for subdir in listdir_fullpath(path):
            if not os.path.isdir(subdir): continue
            manifest.update(index_dicoms(subdir, 
                recurse = recurse, 
                maxdepth = maxdepth - 1, 
                complete = complete))
            if not complete and manifest: break 
    return manifest

def index_exams(paths):
    """ 
    Finds a representative dicom in each path

    The idea is to treat each folder given as an exam folder, and return
    representative dicom for each. The return value is dictionary mapping the path
    to the representative header object.

    The input is a list of paths.
    """
    manifest = {} 
    for examdir in paths: 
        if not os.path.isdir(examdir): continue
        dcm_info = index_dicoms(examdir, maxdepth=1)
        if not dcm_info: continue
        manifest[examdir] = dcm_info.values()[0]
    return manifest 

def find_pfiles(pfile_dir, examdir, examid):
    """
    Finds pfiles that belong as part of an exam. 

    Returns a list of tuples (source, dest), listing files to copy and their
    destination in the examdir. 
    """

    files = []  # (source, dest) list of found files

    pfiles_headers = pfiles.get_all_pfiles_headers(pfile_dir)
    for pfile_path, pfile_headers in pfiles_headers.iteritems():

        # skip irrelvant pfiles
        if str(pfile_headers['exam_number']) != examid: continue
        if ".bak" in pfile_path: continue 
        if "Pfiles_" not in pfile_path: 
            # pfiles not in Pfiles_*/ are likely not sorted correctly
            continue

        # Use a Heuristic to decide what to do with the pfiles found.
        kind = pfiles.guess_pfile_kind(pfile_path, pfile_headers)

        ###
        ## Spectroscopy PFiles
        ###
        if kind == "spectroscopy":   
            # Copy the single pfile to the series folder in inprocess
            # and name the file: Ex#####_Se######_P#####.7
            n     = pfile_headers["series_number"]
            prefix = format_series_name(examid, n, "")

            series_dirs = filter(lambda x: x.startswith(prefix), os.listdir(examdir)) 

            if len(series_dirs) != 1: 
                warn("Couldn't find folder for series {0} in exam dir {1} "
                     "for pfile {2}. Skipping.".format(n,examdir,pfile_path))
                continue

            verbose("Found pfile {0} for series {1}".format(pfile_path, n))
            series_dir = os.path.join(examdir,series_dirs[0])
            dest_name  = format_series_name(examid, n,"") + os.path.basename(pfile_path)
            dest       = os.path.join(series_dir, dest_name)
            files.append((pfile_path, dest))

        ###
        ## fMRI PFiles
        ###
        elif kind == "fmri":
            # Copy the parent folder, and all it contains, to exam in inprocess
            # Name the series folder: Ex#####_Se######_Description
            # Name each of the files: Ex#####_Se######_<originalfilename>
            # Except for sprl.nii: Ex#####_Se######_<pfilename>.nii

            seriesnum   = pfile_headers["series_number"]
            seriesdescr = pfile_headers["series_description"]
            seriesname = format_series_name(examid, seriesnum, seriesdescr)
            
            pfile_name = os.path.basename(pfile_path).replace(".7","").replace(".hdr","")
            pfile_dir  = os.path.dirname(pfile_path)
            series_dir = os.path.join(examdir, seriesname)
            
            for sprlfile in os.listdir(pfile_dir): 
                dest_name = format_series_name(examid, seriesnum, "") + sprlfile
                if sprlfile == 'sprl.nii':
                    dest_name = format_series_name(examid, seriesnum, "") + pfile_name + ".nii"

                source = os.path.join(pfile_dir, sprlfile)
                dest   = os.path.join(series_dir, dest_name)      
                files.append( (source, dest) )

        ###
        ## HOS or "raw" PFiles
        ###
        elif kind == "hos" or kind == "raw": 
            # 3. HOS
            #   - The series_description is "HOS"
            #   - Action: Ignore
            #
            # 4. Raw spiral files
            #   - They are stored in a folder named rawSprlioPfiles
            #   - Action: Move to a raw spiral backup directory
            verbose(
                "Ignoring pfile {0} because it is type == {1}".format(
                pfile_path, kind))
            continue 

        ###
        ## dailyqc files
        ###
        elif kind == "dailyqc":
            seriesnum   = pfile_headers["series_number"]
            dest_name   = format_series_name(examid, seriesnum,"") + os.path.basename(pfile_path)
            dest        = os.path.join(examdir, dest_name)
            files.append((pfile_path, dest))
            
        ###
        ## Unknown Pfiles
        ###
        else: 
            warn("Unknown pfile kind {}: description = {}.".format(pfile_path,
                pfile_headers["series_description"]))

    return files 

def sort_exam(unsorteddir, sorteddir): 
    """
    Determines how to move dicom files into well-named series subfolders. 

    Returns a list of tuples describing each file move operation:
        [ (source, dest), ... ]
    """

    moveoperations = [] 

    dcm_dict = {}  # seq -> [ (path, dcminfo)... ] 
    i = 0   # default used when InstanceNumber isn't in the headers
    for dcm_file in glob.glob(os.path.join(unsorteddir,"*")):
        try: 
            if os.path.isdir(dcm_file): continue 
            ds = dicom.read_file(dcm_file)
        except dicom.filereader.InvalidDicomError, e: 
            verbose("File {} is not a dicom. Skipping.".format(dcm_file))  
            continue  # just skip non-dicom files 

        # Series folder naming: Ex#####Se#####_SeriesDescription, eg.  Ex03806_Se00005_Sag_T1_BRAVO
        # Dicom naming: Ex#####Se#####Im#####.dcm

        examid      = str(ds.get("StudyID"))
        seriesno    = str(ds.get("SeriesNumber", "UNKNOWN"))
        seriesdescr = str(ds.get("SeriesDescription","UNKNOWN"))
        seriesname  = format_series_name(examid, seriesno, seriesdescr)
        instance    = str(ds.get("InstanceNumber",i))
        del ds 

        seriesdir   = os.path.join(sorteddir, seriesname)
        dcmname     = "Ex{examid}Se{seriesno}Im{instance}.dcm".format(
                      examid   = examid.zfill(EXAMID_PADDING),
                      seriesno = seriesno.zfill(SERIESNUM_PADDING),
                      instance = instance.zfill(INSTANCE_PADDING))

        dest_path = os.path.join(seriesdir,dcmname)
        moveoperations.append( (dcm_file, dest_path) )
        i = i + 1

    return moveoperations

def check_exam_for_pfiles(dcm_info): 
    """
    Check that referenced pfiles exist in proper folders in an exam.

    Expects a dictionary mapping a single dicom per series folder to pydicom
    headers. 
    Returns two lists: 

        - directories missing pfiles: [ (dir, pfileid)...]
        - pfiles not matching dir info: [ (pfile path, dcm headers)...]

    """
    missing_pfiles = []
    nonmatching_pfiles = [] 

    series_checked = []
    for dicompath, ds in dcm_info.iteritems():
        series_dir = os.path.dirname(dicompath)

        if series_dir  in series_checked: continue
        series_checked.append(series_dir)

        if DICOM_PRESSCI_KEY not in ds or \
            ds[DICOM_PRESSCI_KEY].value != "presscsi": continue

        pfiles_headers = pfiles.get_all_pfiles_headers(series_dir)
        pfile_id = ds[DICOM_PFILEID_KEY].value

        if len(pfiles_headers) == 0: 
            missing_pfiles.append( (series_dir, pfile_id) )

        for pfile_path, pfile_headers in pfiles_headers.iteritems():
            if str(pfile_headers["exam_number"]) != str(ds.get("StudyID")) or \
               str(pfile_headers["series_number"]) != str(ds.get("SeriesNumber")):
                nonmatching_pfiles.append( (pfile_path, ds) )


    return missing_pfiles, nonmatching_pfiles

def get_output_dir(examinfo, output_dir, tech_dir, dailyqc_dir): 
    """
    Determine the proper output directory for the exam. 

    <exam> is a dictionary of dicom headers for the exam. 
    """

    # At the moment, we'll use the heuristic that if the study description
    # doesn't end with MR or QA, it's a technologist exam. 
    # See https://github.com/TIGRLab/mritool/issues/14
    descr = examinfo.get("StudyDescription","")

    if descr == 'DailyQC': 
        return dailyqc_dir

    if not (descr.endswith("MR") or descr.endswith("QA")):
        return tech_dir

    return output_dir

####
# Command line operations 
###########################################

def pull_exams(arguments): 
    """ Command to pull exams from the scanner. """
    examid        = arguments['<exam>']
    seriesno      = arguments['<series>']
    output_dir    = arguments['-o'] or arguments['--inprocess-dir']
    tech_dir      = arguments['--tech-dir']
    pfile_dir     = arguments['--pfile-dir'] 
    dailyqc_dir   = arguments['--dailyqc-dir']
    bare          = arguments['--bare']
    connection    = _get_scanner_connection(arguments)

    query    = scu.StudyQuery(StudyID = examid)
    examinfo = connection.find(query)

    if not examinfo: 
        warn("Exam {} not found on the scanner. Skipping.".format(examid))
        return 

    if not arguments['-o']:
        output_dir = get_output_dir(examinfo[0], output_dir, tech_dir, dailyqc_dir)

    debug("Using {} output folder.".format(examid, output_dir))

    if not os.access(output_dir, os.W_OK): 
        fatal("No write access to output folder {}. Exiting.".format(output_dir))
        
    if seriesno: 
        query      = scu.SeriesQuery(StudyID = examid, SeriesNumber = seriesno)
        seriesinfo = connection.find(query)

        if not seriesinfo: 
            warn("Exam {}, series {} not found on the scanner. Skipping.".format(
                examid, seriesno))
            return 
        log("Pulling exam {}, series {} to {}".format(examid, seriesno, output_dir))
    else:
        log("Pulling exam {} to {}".format(examid, output_dir))

    _pull_exam(connection, examinfo[0], output_dir, pfile_dir, query, bare=bare)

def _pull_exam(connection, examinfo, output_dir, pfile_dir, query, bare=None):
    """Internal method to pull exam data from the scanner. 

    <examinfo> is dictionary of exam details.
    """

    studydescr = examinfo.get("StudyDescription","UNKNOWN")
    examid     = examinfo.get("StudyID")

    ###
    ## Set up   
    ### 
    examdirname = format_exam_name(examinfo) 
    examdir     = os.path.join(output_dir,examdirname)
   
    ###
    ## Copy dicoms from the scanner, and organize them into series folders
    ###
    tempdir = tempfile.mkdtemp()
    debug("Fetching DICOMS into {0}".format(tempdir))

    try:
        connection.move(query, tempdir)
    except subprocess.CalledProcessError as ex: 
        log("Dicom transfer failed: {}".format(ex.output))
        return 

    # move dicom files into folders
    debug("Sorting dicoms from {} into {}".format(tempdir, examdir))
    if not os.path.exists(examdir): os.makedirs(examdir) 
    _sort_exam(tempdir, examdir)
    shutil.rmtree(tempdir)

    # fetch all non-dicom data for the exam
    if not bare:
        _fetch_nondicom_exam_data(examdir, examid, pfile_dir)

def _sort_exam(unsorteddir, sorteddir): 
    """ Internal function rename dicoms into series folders. """
    # move dicom files into folders
    moveops = sort_exam(unsorteddir, sorteddir)
    for source, dest in moveops: 
        debug("Moving {} to {}".format(source, dest))
        if not os.path.exists(os.path.dirname(dest)): 
            os.makedirs(os.path.dirname(dest))
        shutil.copyfile(source,dest)

def _fetch_nondicom_exam_data(examdir, examid, pfile_dir): 
    """ Find perhipheral data """
    ###
    ## Copy pFiles and related pfile assets
    ###
    debug("Searching for pfiles matching this exam...")
    copyops = find_pfiles(pfile_dir, examdir, examid)
    for source, dest in copyops: 
        debug("Copying {} to {}".format(source, dest))
        directory = os.path.dirname(dest)
        if not os.path.exists(directory): 
            os.makedirs(directory)
        shutil.copy(source, dest)

    ###
    ## Check dicom headers for related pfiles
    ##
    ## A dicom series with an asssociated pfile has the DICOM_PRESSCI_KEY
    ## header set to "presssci".  
    ###
    debug("Checking whether all pfiles have been found...")
    dicom_info = index_dicoms(examdir)
    missing_pfiles, nonmatching_pfiles = check_exam_for_pfiles(dicom_info) 
    for series_dir, pfile_id in missing_pfiles:
        warn("Expected pfile (id: {}) in {} but none were found.".format(
            pfile_id, series_dir))
    for pfile_path, dcm_headers in nonmatching_pfiles:
        warn("Pfile {} headers do not match exam/series number.".format(
            pfile_path))
        
def package_exams(arguments): 
    processed_dir = arguments['--processed-dir']
    inprocess_dir = arguments['--inprocess-dir']
    pfile_dir     = arguments['--pfile-dir'] 
    log_dir       = arguments['--log-dir'] 
    examid        = arguments['<exam>']
    connection    = _get_scanner_connection(arguments)

    if not os.path.exists(processed_dir): os.makedirs(processed_dir)

    # look in inprocess for <bookingcode>/.*E<examid>_.* folders
    inprocess_exams = index_exams(listdir_fullpath(inprocess_dir))
    inprocess_by_id = { ds.get("StudyID") : path for path, ds in inprocess_exams.iteritems() } 

    if examid not in inprocess_by_id: 
        fatal("Unable to find exam {0} in the inprocess dir {1}. Skipping.".format(
            examid, inprocess_dir))
        return
    examdir  = inprocess_by_id[examid]
    examstem = os.path.basename(examdir)
    destdir  = os.path.join(processed_dir, examstem)

    warnings = _check_inprocess(examid, examdir, connection)
    
    if os.path.exists(destdir):
        warn("{0} folder already exists. Skipping.".format(destdir))
        return

    for warning in warnings: warn(warning)

    if warnings and not arguments['--force']: 
        warn("Not packaging exam {} because of warnings. Use --force to do it anyway".format(
            examid))
        return

    log("Moving exam {0} to {1}".format(examid, destdir))
    shutil.move(examdir, processed_dir)

    verbose("Setting read-only permissions on {0}".format(destdir))
    try:
        output = subprocess.check_output(
            shlex.split('chmod -R ugo-w "{}"'.format(destdir)))
    except subprocess.CalledProcessError as ex:
        fatal("Error setting read-only permissions on completed scan.\n{}\n".format(
            ex.output))

            
def list_exams(arguments): 
    processed_dir = arguments['--processed-dir']
    inprocess_dir = arguments['--inprocess-dir']

    connection = _get_scanner_connection(arguments)

    records    = connection.find(scu.StudyQuery())

    headers = [ "StudyID", "StudyDate", "PatientID", "StudyDescription", "PatientName"] 
    table   = [ { key : r.get(key,"") for key in headers } for r in records ]

    def filter_exams(row):
        """Filter the exams by user filters."""
        code = arguments['-b']
        exam = arguments['-e']
        date = arguments['-d']

        if date and not fnmatch.fnmatch(row['StudyDate'],date): return False
        if exam and not fnmatch.fnmatch(row['StudyID'],exam): return False
        if code and not fnmatch.fnmatch(row['StudyDescription'],code): return False
        return True

    table = filter(filter_exams, table)
        
        
    # check if inprocess
    headers = headers + ["Staged"]
    for row in table: 
        studyid = row['StudyID']
        row["Staged"] = glob.glob(inprocess_dir+"/*_Ex"+studyid+"_*") and "yes" or "no"
    
    # sort, de-dictionary and print
    table  = sorted(table, key=lambda row: int(row['StudyID']))
    table  = [ [r[h] for h in headers]  for r in table ]
    log("\n{}\n".format(tabulate.tabulate(table, headers=headers)))

def list_series(arguments):
    """
    List the series for an exam. 
    """
    examid     = arguments['<exam>']
    connection = _get_scanner_connection(arguments)
    records    = connection.find(scu.SeriesQuery(StudyID = examid))

    headers = "SeriesNumber", "SeriesDescription","ImagesInAcquisition"
    table = [ [ r.get(key,"") for key in headers ] for r in records ]
    table = sorted(table, key=lambda row: int(row[0]))

    log("\n{}\n".format(tabulate.tabulate(table, headers=headers)))

def show_inprocess(arguments): 
    """
    Show the exams in the inprocess area.
    """

    processed_dir  = arguments['--processed-dir']
    inprocess_dir= arguments['--inprocess-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 
    
    dicom_headers = ["StudyID", "StudyDate", "PatientID", "StudyDescription", "PatientName"]
    headers = ["Path"] + dicom_headers
    table = [] 

    for examdir, ds in index_exams(listdir_fullpath(inprocess_dir)).iteritems(): 
        row = [examdir]    # Path
        for header in dicom_headers:
            row.append(ds.get(header,""))
        table.append(row)         

    table = sorted(table, key=lambda row: int(row[1]))   #  sort by study id 
    log("\n{}\n".format(tabulate.tabulate(table, headers=headers)))

def check_series_dicoms(examdir, examid, seriesinfo):
    """
    Checks that all series are present with correct dicom files. 

    <seriesinfo> is a list of dictionaries for each expected series. The
    dictionary for a series contains Dicom attributes: StudyID, SeriesNumber,
    SeriesDescription, ImagesInAcquistion.

    Returns an empty list if all checks pass, and a list of user warnings
    otherwise. 
    """

    warnings = [] 

    for info in seriesinfo: 
        series      = info.get("SeriesNumber","")
        seriesdescr = info.get("SeriesDescription","UNKNOWN")
        numimages   = int(info.get("ImagesInAcquisition",0))
        seriesname  = format_series_name(examid, series, seriesdescr)
        seriesdir   = os.path.join(examdir, seriesname)

        # Confirm series folder exists, if it doesn't: warn
        if not os.path.exists(seriesdir):
            warnings.append("Exam {}: expected series folder {} does not exist.".format(
                examid, seriesdir))
            continue

        # Confirm series folder has dicom data in it that matches the series
        dicoms = glob.glob(seriesdir+"/*.dcm")

        if len(dicoms) != numimages:
            warnings.append("Series {} has {} dicoms, expected {}.".format(
                seriesdir, len(dicoms), numimages))
            continue

    return warnings

def check_inprocess(arguments):
    """
    Check that a inprocess exam is complete. 

    This checks for the following things: 
        - Each series is present (if possible)
        - Each series has the expected number of dicom files
        - All pfile data is present
        - All physio data is present
    """
    processed_dir = arguments['--processed-dir']
    inprocess_dir = arguments['--inprocess-dir']
    pfile_dir     = arguments['--pfile-dir'] 
    log_dir       = arguments['--log-dir'] 
    examid        = arguments['<exam>']
    connection    = _get_scanner_connection(arguments)

    inprocess_exams = index_exams(listdir_fullpath(inprocess_dir))
    inprocess_by_id = { ds.get("StudyID") : path for path, ds in inprocess_exams.iteritems() } 

    if examid not in inprocess_by_id:
        warn("Unable to find exam {0} in the inprocess dir {1}. Skipping.".format(
            examid, inprocess_dir))
        return

    examinfo = inprocess_exams[inprocess_by_id[examid]]
    examname = format_exam_name(examinfo)
    examdir  = os.path.join(inprocess_dir, examname)
    warnings = _check_inprocess(examid, examdir, connection)

    for warning in warnings: warn(warning)
    if not warnings: log("All dicom files present for exam {}".format(examid))

def sync(arguments):
    """ Pulls all unpulled exams into the processing folder. """
    log_dir       = arguments['--log-dir'] 
    inprocess_dir = arguments['--inprocess-dir']
    tech_dir      = arguments['--tech-dir']
    dailyqc_dir   = arguments['--dailyqc-dir']
    pfile_dir     = arguments['--pfile-dir'] 

    # attach sync.log handler
    logfile = os.path.join(log_dir, 'sync.log')
    fh = logging.FileHandler(logfile)
    fh.setLevel(logging.INFO)
    logging.getLogger().addHandler(fh)

    # begin
    log("Starting sync: {}".format(datetime.datetime.now()))
    pulled  = []
    logfilepath = os.path.join(log_dir, 'exams.txt')
    if os.path.exists(logfilepath): 
        pulled = open(logfilepath,'r').read().split("\n")

    logfile = open(logfilepath,'a')
    connection = _get_scanner_connection(arguments)

    for exam in  connection.find(scu.StudyQuery()):
        examid = exam.get("StudyID","")
        if not examid or examid in pulled or int(examid) > MIN_SERVICE_EXAM_NUM: 
            continue

        output_dir = get_output_dir(exam, inprocess_dir, tech_dir, dailyqc_dir)
        debug("Using {} output folder.".format(examid, output_dir))

        query = scu.StudyQuery(StudyID = examid)
        log("Pulling exam {} to {}".format(examid, output_dir))
        _pull_exam(connection, exam, output_dir, pfile_dir, query)
        logfile.write(exam['StudyID']+'\n')
    
def _get_scanner_connection(arguments): 
    host       = arguments['--host']
    port       = arguments['--port']
    aet        = arguments['--aet']
    aec        = arguments['--aec']
    rport      = port    # return port is the same (for now)
    return scu.SCU(host, port, rport, aet, aec) 

def _check_inprocess(examid, examdir, connection):
    """
    Internal method for doing all checks on a inprocess exam. See check_inprocess

    Returns [] if successful, and a list of user warnings otherwise
    """
    warnings = []

    ####
    # Check that each series is present and has expected # of dicoms
    seriesinfo = connection.find(scu.SeriesQuery(StudyID = examid))
    if not seriesinfo: 
        warnings.append(
            "Exam {} not on scanner. Unable to check series count.".format(
                examid))

    warnings.extend(check_series_dicoms(examdir, examid, seriesinfo))

    ####
    # Check that all pfile data is present
    dicom_info = index_dicoms(examdir)
    missing_pfiles, nonmatching_pfiles = check_exam_for_pfiles(dicom_info) 
    for series_dir, pfile_id in missing_pfiles:
        warnings.append(
            "Expected pfile (id: {}) in {} but none were found.".format(
                pfile_id, series_dir))
    for pfile_path, dcm_headers in nonmatching_pfiles:
        warnings.append(
            "Pfile {} headers do not match exam/series number.".format(
                pfile_path))
    
    return warnings

def pfile_headers(path): 
    """ Dump out the headers for a pfile """
    headers = pfiles.get_pfile_headers(path)     
    if not headers: 
        warn("{} is not a pfile.".format(path))
        return
    table = []
    for k,v in headers.iteritems(): 
        try:
            table.append([str(k).decode('ascii'), str(v).decode('ascii')]) 
        except: pass

    print
    print tabulate.tabulate(table, headers= ["Header", "Value"])
    print
    
def main(): 
    global VERBOSE
    global DEBUG

    defaults = UserDict.UserDict()
    defaults['raw']       = os.environ.get("MRITOOL_RAW_DIR"      ,"./input/scanner")
    defaults['inprocess'] = os.environ.get("MRITOOL_INPROCESS_DIR","./output/inprocess")
    defaults['processed'] = os.environ.get("MRITOOL_PROCESSED_DIR","./output/processed")
    defaults['tech']      = os.environ.get("MRITOOL_TECH_DIR"     ,"./output/tech")
    defaults['dailyqc']   = os.environ.get("MRITOOL_DAILYQC_DIR"  ,"./output/DailyQC")
    defaults['logs']      = os.environ.get("MRITOOL_LOGS_DIR"     ,"./output/logs")
    defaults['host']      = os.environ.get("MRITOOL_HOST"         ,"CAMHMR")
    defaults['port']      = os.environ.get("MRITOOL_PORT"         ,"4006")
    defaults['aet']       = os.environ.get("MRITOOL_AET"          ,"mrsrv1")
    defaults['aec']       = os.environ.get("MRITOOL_AEC"          ,"CAMHMR")
    options = """ 
Finds and copies exam data into a well-organized folder structure.

Usage: 
    mritool [options] pull <exam> [<series>] [-o <outputdir>] [--bare]
    mritool [options] check <exam>
    mritool [options] complete <exam>
    mritool [options] list-exams [-b <booking_code>] [-e <exam>] [-d <date>]
    mritool [options] list-series <exam>
    mritool [options] list-inprocess
    mritool [options] sync-exams
    mritool pfile-headers <pfile>
    mritool help 

Commands: 
    pull                      Get an exam from the scanner
    check                     Check that an exam being processed has all of its files
    complete                  Mark an exam as complete by moving it to the processed folder
    list-exams                List all exams on the scanner
    list-series               List all series for the exam on the scanner
    list-inprocess            List the exams in the inprocess area
    sync-exams                Pulls all unpulled exams into the processing folder
    pfile-headers             Show the headers of a pfile
    help                      Display this help.
 
Command options: 
    -b <bookingcode>          Booking code (StudyDescription)
    -d <date>                 Date (StudyDate)
    -e <exam>                 Exam number (StudyID)
    -o <outputdir>            Output directory (overrides --inprocess-dir)
    --bare                    Only pull dicom files

Global options: 
    --inprocess-dir=<dir>     In-process exams directory [default: {defaults[inprocess]}]
    --processed-dir=<dir>     Processed exams directory [default: {defaults[processed]}]
    --log-dir=<dir>           Logging directory [default: {defaults[logs]}]
    --pfile-dir=<dir>         Pfile directory [default: {defaults[raw]}]
    --tech-dir=<dir>          Technologist scans [default: {defaults[tech]}]
    --dailyqc-dir=<dir>       DailyQC scans [default: {defaults[dailyqc]}]
    --host=<str>              Scanner hostname [default: {defaults[host]}]
    --port=<num>              Scanner port [default: {defaults[port]}]
    --aet=<str>               Scanner AET [default: {defaults[aet]}]
    --aec=<str>               Calling machine AEC [default: {defaults[aec]}]
    -f, --force               Force a command, even if there are warnings
    -v, --verbose             Verbose messages
    --debug                   Debug messages 
""".format(defaults=defaults)

    arguments = docopt(options)

    VERBOSE = arguments['--verbose']
    DEBUG   = arguments['--debug']

    logger.setLevel(logging.INFO)

    if DEBUG: 
        logger.setLevel(logging.DEBUG)
    
    if arguments['pull']:
        pull_exams(arguments)
    if arguments['check']:
        check_inprocess(arguments)
    if arguments['complete']:
        package_exams(arguments)
    if arguments['list-exams']:
        list_exams(arguments)
    if arguments['list-inprocess']:
        show_inprocess(arguments)
    if arguments['list-series']:
        list_series(arguments)
    if arguments['sync-exams']:
        sync(arguments)
    if arguments['pfile-headers']:
        pfile_headers(arguments['<pfile>'])
    if arguments['help']: 
        print options
    
if __name__ == "__main__":
    main()
