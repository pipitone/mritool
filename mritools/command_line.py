#!/bin/env python
# vim: expandtab ts=4 sw=4 tw=80: 
import pfiles
import scu
from docopt import docopt
import shutil
import tabulate
import logging
import os
import pwd
import os.path
import dicom
import glob 
import sys
import UserDict
import re
import traceback 
import zipfile
from collections import defaultdict

VERBOSE = False
DRYRUN = False
DICOM_PRESSCI_KEY = 0x0019109e
DICOM_PFILEID_KEY = 0x001910a2
EXAMID_PADDING = 5      # Zero pad chars when formatting exam IDs
SERIESNUM_PADDING = 5   # Zero pad chars when formatting exam series numbers 
INSTANCE_PADDING = 5    # Zero pad chars when formatting dicom instance numbers

####
#  Logging
###########################################
logging.basicConfig(
        format='%(asctime)s %(name)16.16s:%(levelname)4.4s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        )

def fatal(message, exception = None): 
    print "FATAL: {0}".format(message)
    if exception: 
        print traceback.print_exc(exception)
    sys.exit(1)

def warn(message): 
    print "WARNING: {0}".format(message)

def verbose(message):
    if VERBOSE: log(message)

def log(message): 
    print "{0}".format(message)

def run(command): 
    verbose("EXEC: " + command)
    if DRYRUN: return 
    os.system(command)

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
    bookingcode  = examinfo.get("StudyDescription","")    # by default this is the booking code
    if bookingcode.split(" ")[0].startswith("e+"):  
        ammendment   = bookingcode.split(" ")[0]
        bookingcode  = " ".join(bookingcode.split(" ")[1:])
       
    return "{date}_Ex{examid}_{bookingcode}_{patientid}{ammendment}".format(
              date        = examinfo.get("StudyDate"),
              examid      = examinfo.get("StudyID"),
              bookingcode = mangle(bookingcode),
              patientid   = mangle(examinfo.get("PatientID","")), 
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
            if not os.path.isdir(filepath): continue
            manifest.update(index_dicoms(subdir, 
                recurse = recurse, 
                maxdepth = maxdepth - 1, 
                complete = complete))
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
        dcm_info = index_dicoms(examdir)
        if not dcm_info: continue
        manifest[examdir] = dcm_info.values()[0]
    return manifest 

def find_pfiles(pfile_dir, examdir, examid):
    """
    Finds pfiles that belong as part of an exam. 

    Returns a list of tuples (source, dest) listening files to copy and their
    destination in the examdir. 
    """

    files = []  # (source, dest) list of found files

    pfiles_headers = pfiles.get_all_pfiles_headers(pfile_dir)
    for pfile_path, pfile_headers in pfiles_headers.iteritems():

        # skip irrelvant pfiles
        if str(pfile_headers['exam_number']) != examid: continue
        if ".bak" in pfile_path: continue 

        # Use a Heuristic to decide what to do with the pfiles found.
        kind = pfiles.guess_pfile_kind(pfile_path, pfile_headers)

        ###
        ## Spectroscopy PFiles
        ###
        if kind == "spectroscopy":   
            # Copy the single pfile to the series folder in staging
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
            # Copy the parent folder, and all it contains, to exam in staging
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
        ## Unknown Pfiles
        ###
        else: 
            warn("Unknown pfile kind {}: description = {}.".format(pfile_path,
                pfile_headers["series_description"]))

    return files 

def sort_exam(examdir): 
    """
    Determines how to move dicom files into well-named series subfolders. 

    Returns a list of tuples describing each file move operation:
        [ (source, dest), ... ]
    """

    dcm_dict = {}  # seq -> [ (path, dcminfo)... ] 
    for dcm_file in glob.glob(os.path.join(examdir,"*")):
        try: 
            if os.path.isdir(dcm_file): continue 
            ds = dicom.read_file(dcm_file)
        except dicom.filereader.InvalidDicomError, e: 
            verbose("File {} is not a dicom. Skipping.".format(dcm_file))  
            continue  # just skip non-dicom files 

        if "SeriesNumber" not in ds:
            verbose("Dicom {} does not have a SeriesNumber. Skipping.".format(dcm_file))  
            continue  # skip 
        seq = str(ds.get("SeriesNumber"))
        dcm_dict.setdefault(seq, []).append( (dcm_file,ds) )


    moveoperations = [] 

    # Series folder naming: Ex#####Se#####_SeriesDescription, eg.  Ex03806_Se00005_Sag_T1_BRAVO
    # Dicom naming: Ex#####Se#####Im#####.dcm
    for seq, filedata in dcm_dict.iteritems(): 
        _, ds = filedata[0]   # take the first in the series
        examid = ds.get("StudyID")
        seriesdescr = ds.get("SeriesDescription","")
        seriesname = format_series_name(examid, seq, seriesdescr)
        seriesdir  = os.path.join(examdir, seriesname)

        i = 0
        for dcmpath, ds in filedata:
            instance = str(ds.get("InstanceNumber",i))
            dcmname = "Ex{examid}Se{series}Im{instance}.dcm".format(
                        examid=examid.zfill(5),series=seq.zfill(5),instance=instance.zfill(5))
            dest_path = os.path.join(seriesdir,dcmname)
            moveoperations.append( (dcmpath, dest_path) )
            i += 1

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

def zipdir(path, ziph):
    """
    Zips up a path (including subdirs and files)

    ziph is zipfile handle
    """

    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file))

####
# Command line operations 
###########################################

def pull_exams(arguments): 
    examids    = arguments['<exam_number>']
    staging_dir= arguments['--staging-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 
    connection = _get_scanner_connection(arguments)

    for examid in examids:
        examinfo   = connection.find(scu.StudyQuery(StudyID = examid))
        if not examinfo: 
            warn("Exam {} not found on the scanner. Skipping.".format(examid))
            continue
        examinfo = examinfo[0]
        studydescr = examinfo.get("StudyDescription","")

        ###
        ## Set up   
        ### 
        examdirname = format_exam_name(examinfo) 
        examdir  = os.path.join(staging_dir,examdirname)
        
        log("Considering exam {}, description: '{}' ...".format(examid, studydescr))
        
        ###
        ## Copy dicoms from the scanner, and organize them into series folders
        ###
        if os.path.isdir(examdir):  
            verbose("Exam {0} folder exists {1}. Skipping.".format(examid, examdir)) 
        else:
            log("Fetching DICOMS into {0}".format(examdir))
            os.makedirs(examdir) 
            if not DRYRUN: connection.move(scu.StudyQuery(StudyID = examid), examdir)

            # move dicom files into folders
            _sort_exam(examdir)

        # fetch all non-dicom data for the exam
        _fetch_nondicom_exam_data(examdir, examid, pfile_dir)

def pull_series(arguments): 
    examid     = arguments['<exam_number>'][0]
    seriesno   = arguments['<series_number>']
    outputdir  = arguments['<outputdir>'] or '.'
    pfile_dir  = arguments['--pfile-dir'] 
    connection = _get_scanner_connection(arguments)

    exams = connection.find(scu.StudyQuery(StudyID = examid))
    if not exams: 
        warn("Can't find exam {}".format(examid))
        return
    examinfo = exams[0]

    seriesq = scu.SeriesQuery(StudyID = examid, SeriesNumber = seriesno)
    series = connection.find(seriesq)

    if not series: 
        warn("Can't find series {} in exam {}".format(examid, seriesno))
        return

    examname = format_exam_name(examinfo)
    examdir  = os.path.join(outputdir, examname)
    if not os.path.exists(examdir): os.makedirs(examdir)
    connection.move(seriesq, examdir)
    _sort_exam(examdir)
    _fetch_nondicom_exam_data(examdir, examid, pfile_dir)

def _sort_exam(examdir): 
    """ Internal function rename dicoms into series folders. """
    # move dicom files into folders
    moveops = sort_exam(examdir)
    for source, dest in moveops: 
        verbose("Moving {} to {}".format(source, dest))
        if not os.path.exists(os.path.dirname(dest)): 
            os.makedirs(os.path.dirname(dest))
        if not DRYRUN: shutil.move(source,dest)

def _fetch_nondicom_exam_data(examdir, examid, pfile_dir): 
    """ Find perhipheral data """
    ###
    ## Copy pFiles and related pfile assets
    ###
    verbose("Searching for pfiles matching this exam...")
    copyops = find_pfiles(pfile_dir, examdir, examid)
    for source, dest in copyops: 
        verbose("Copying {} to {}".format(source, dest))
        directory = os.path.dirname(dest)
        if not os.path.exists(directory): 
            os.makedirs(directory)
        if not DRYRUN: shutil.copy(source, dest)

    ###
    ## Check dicom headers for related pfiles
    ##
    ## A dicom series with an asssociated pfile has the DICOM_PRESSCI_KEY
    ## header set to "presssci".  
    ###
    verbose("Checking whether all pfiles have been found...")
    dicom_info = index_dicoms(examdir)
    missing_pfiles, nonmatching_pfiles = check_exam_for_pfiles(dicom_info) 
    for series_dir, pfile_id in missing_pfiles:
        warn("Expected pfile (id: {}) in {} but none were found.".format(
            pfile_id, series_dir))
    for pfile_path, dcm_headers in nonmatching_pfiles:
        warn("Pfile {} headers do not match exam/series number.".format(
            pfile_path))
        
def package_exams(arguments): 
    scans_dir  = arguments['--scans-dir']
    staging_dir= arguments['--staging-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 
    connection = _get_scanner_connection(arguments)

    if not os.path.exists(scans_dir): os.makedirs(scans_dir)

    # look in staging for <bookingcode>/.*E<examid>_.* folders
    staged_exams = index_exams(listdir_fullpath(staging_dir))
    staged_by_id = { ds.get("StudyID") : path for path, ds in staged_exams.iteritems() } 

    for examid in arguments['<exam_number>']: 
        if examid not in staged_by_id: 
            fatal("Unable to find exam {0} in the staging dir {1}. Skipping.".format(
                examid, staging_dir))
            continue
        examdir = staged_by_id[examid]
        exam_name = os.path.basename(examdir)
        pkg_path  = "{0}/{1}.zip".format(scans_dir,exam_name)

        warnings = _check_staged(examid, examdir, connection)
        
        if os.path.exists(pkg_path):
            warnings.append(
                "{0} zip already exists. Skipping.".format(pkg_path))

        for warning in warnings: warn(warning)

        if warnings and not arguments['--force']: 
            warn("Not packaging exam {} because of warnings. Use --force to do it anyway".format(
                examid))
            continue


        log("Packing exam {0} as {1}".format(examid, pkg_path))
        ziph = zipfile.ZipFile(pkg_path,'w')
        zipdir(examdir,ziph)
        ziph.close()
            
def list_exams(arguments): 
    scans_dir  = arguments['--scans-dir']
    staging_dir= arguments['--staging-dir']
    connection = _get_scanner_connection(arguments)
    records    = connection.find(scu.StudyQuery())

    headers = [ "StudyID", "StudyDate", "PatientID", "StudyDescription", "PatientName"] 
    table = [ [ r.get(key,"") for key in headers ] for r in records ]
    table = sorted(table, key=lambda row: int(row[0]))

    if arguments["<number>"]:
        table = table[-int(arguments["<number>"]):]

    # check if zipped or staged
    headers = headers + ["Staged", "Zipped"]
    for row in table: 
        studyid = row[0]
        staged = glob.glob(staging_dir+"/*_Ex"+studyid+"_*") and "yes" or "no"
        zipped = glob.glob(scans_dir+"/*_Ex"+studyid+"_*") and "yes" or "no"
        row.extend( [ staged, zipped] ) 

    print
    print tabulate.tabulate(table, headers=headers )
    print

def list_series(arguments):
    """
    List the series for an exam. 
    """
    examid     = arguments['<exam_number>'][0]   
    connection = _get_scanner_connection(arguments)
    records    = connection.find(scu.SeriesQuery(StudyID = examid))

    headers = "SeriesNumber", "SeriesDescription","ImagesInAcquisition"
    table = [ [ r.get(key,"") for key in headers ] for r in records ]
    table = sorted(table, key=lambda row: int(row[0]))

    print
    print tabulate.tabulate(table, headers=headers)
    print

def show_staged(arguments): 
    """
    Show the exams in the staging area.
    """

    scans_dir  = arguments['--scans-dir']
    staging_dir= arguments['--staging-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 
    
    dicom_headers = ["StudyID", "StudyDate", "PatientID", "StudyDescription", "PatientName"]
    headers = ["Path"] + dicom_headers + ["Zipped"]
    table = [] 

    for examdir, ds in index_exams(listdir_fullpath(staging_dir)).iteritems(): 
        row = [examdir]    # Path
        for header in dicom_headers:
            row.append(ds.get(header,""))
        exam_name = os.path.basename(examdir)
        pkg_path  = "{0}/{1}.zip".format(scans_dir,exam_name)
        row.append(os.path.exists(pkg_path) and "yes" or "no")
        table.append(row)         

    table = sorted(table, key=lambda row: int(row[1]))   #  sort by study id 
    print
    print tabulate.tabulate(table, headers=headers )
    print

def show_zipped(arguments): 
    """
    Show the exams in the staging area.
    """

    scans_dir  = arguments['--scans-dir']
    staging_dir= arguments['--staging-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 
    
    headers = ["Path", "Staged"]
    table = [] 

    for zip in glob.glob(scans_dir + "/*.zip"):
        row = [zip]    # Path
        examname = os.path.basename(zip).replace(".zip","")
        row.append(os.path.exists(staging_dir + "/" + examname) and "yes" or "no")
        table.append(row)         

    table = sorted(table, key=lambda row: row[0]) 
    print 
    print tabulate.tabulate(table, headers=headers )
    print 

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
        seriesdescr = info.get("SeriesDescription","")
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

def check_staged(arguments):
    """
    Check that a staged exam is complete. 

    This checks for the following things: 
        - Each series is present (if possible)
        - Each series has the expected number of dicom files
        - All pfile data is present
        - All physio data is present
    """
    scans_dir  = arguments['--scans-dir']
    staging_dir= arguments['--staging-dir']
    pfile_dir  = arguments['--pfile-dir'] 
    log_dir    = arguments['--log-dir'] 
    connection = _get_scanner_connection(arguments)

    staged_exams = index_exams(listdir_fullpath(staging_dir))
    staged_by_id = { ds.get("StudyID") : path for path, ds in staged_exams.iteritems() } 

    for examid in arguments['<exam_number>']: 
        if examid not in staged_by_id: 
            warn("Unable to find exam {0} in the staging dir {1}. Skipping.".format(
                examid, staging_dir))
            continue

        examinfo = staged_exams[staged_by_id[examid]]
        examname = format_exam_name(examinfo)
        examdir  = os.path.join(staging_dir, examname)
        warnings = _check_staged(examid, examdir, connection)

        for warning in warnings: warn(warning)
        if not warnings: print "All dicom files present for exam {}".format(examid)

def _get_scanner_connection(arguments): 
    host       = arguments['--host']
    port       = arguments['--port']
    aet        = arguments['--aet']
    aec        = arguments['--aec']
    rport      = port    # return port is the same (for now)
    return scu.SCU(host, port, rport, aet, aec) 

def _check_staged(examid, examdir, connection):
    """
    Internal method for doing all checks on a staged exam. See check_staged

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
    
def main(): 
    global DRYRUN 
    global VERBOSE

    defaults = UserDict.UserDict()
    defaults['raw']     = os.environ.get("MRITOOL_RAW_DIR"    ,"/mnt/mrraw/camh")
    defaults['staging'] = os.environ.get("MRITOOL_STAGING_DIR","/data/mritooltest/InProcess")
    defaults['scans']   = os.environ.get("MRITOOL_SCANS_DIR"  ,"/data/mritooltest/Processed")
    defaults['logs']    = os.environ.get("MRITOOL_LOGS_DIR"   ,"/data/mritooltest/logs")
    defaults['host']    = os.environ.get("MRITOOL_HOST"       ,"CAMHMR")
    defaults['port']    = os.environ.get("MRITOOL_PORT"       ,"4006")
    defaults['aet']     = os.environ.get("MRITOOL_AET"        ,"mr-srv1")
    defaults['aec']     = os.environ.get("MRITOOL_AEC"        ,"CAMHMR")
    options = """ 
Finds and copies exam data into a well-organized folder structure.

Usage: 
    mritool [options] pull-exams <exam_number>... 
    mritool [options] pull-series <exam_number> <series_number> [<outputdir>]
    mritool [options] list-exams [<number>] 
    mritool [options] list-series <exam_number>
    mritool [options] list-staged
    mritool [options] list-zipped 
    mritool [options] check-staged <exam_number>...
    mritool [options] zip <exam_number>...
    mritool [options] rm <exam_number>...

Commands: 
    pull-exams                 Get an exam from the scanner
    pull-series                Get a single series from the scanner
    list-exams                 List all exams on the scanner
    list-series                List all series for the exam on the scanner
    list-staged                List the exams in the staging area
    list-zipped                List the exams that have been zipped
    check-staged               Check that a staged exam has all of its files
    rm                         Remove exam data from the staging area
    zip                        Zip up exam

Options: 
    --scans-dir=<dir>          Staging directory [default: {defaults[scans]}]
    --staging-dir=<dir>        Staging directory [default: {defaults[staging]}]
    --log-dir=<dir>            Logging directory [default: {defaults[logs]}]
    --pfile-dir=<dir>          Pfile directory [default: {defaults[raw]}]
    --host=<str>               Scanner hostname [default: {defaults[host]}]
    --port=<num>               Scanner port [default: {defaults[port]}]
    --aet=<str>                Scanner AET [default: {defaults[aet]}]
    --aec=<str>                Calling machine AEC [default: {defaults[aec]}]
    -f, --force                Force a command, even if there are warnings.
    -n, --dry-run              Do nothing, but show what would be done. 
    -v, --verbose              Verbose messaging.

""".format(defaults=defaults)

    arguments = docopt(options)

    DRYRUN = arguments['--dry-run']
    VERBOSE = arguments['--verbose']
    
    if arguments['list-exams']:
        list_exams(arguments)
    if arguments['list-staged']:
        show_staged(arguments)
    if arguments['list-zipped']:
        show_zipped(arguments)
    if arguments['list-series']:
        list_series(arguments)
    if arguments['pull-exams']:
        pull_exams(arguments)
    if arguments['pull-series']:
        pull_series(arguments)
    if arguments['zip']:
        package_exams(arguments)
    if arguments['check-staged']:
        check_staged(arguments)
    
if __name__ == "__main__":
    main()
