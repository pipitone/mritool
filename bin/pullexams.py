#!/bin/env python
# vim: expandtab ts=4 sw=4 tw=80: 
import os
import os.path
import datetime 
import dicom

STAGING_DIR = "./data/scans"
LOGS_DIR    = "./data/scans/logs"

for line in os.popen("getallstudycodes | grep DTIG | tail -1"):     	
    (examid, studycode, date, patient_id, patient_name) = line.split()
    
    studydir    = STAGING_DIR +"/" + studycode
    examdirname = "{studycode}_E{examid}_{date}_{patient_id}_{patient_name}" \
                    .format(**vars())
    examdir     = "{studydir}/{examdirname}".format(**vars())
    exam_tarball= "{0}/{1}.tar.gz".format(studydir, examdirname)
    examinfo    = "{0}/{1}.info".format(studydir, examdirname)
    
    print "Considering exam {0} from study {1}... ".format(
        examid, studycode),

    # Create the study directory if it doesn't exist 
    if not os.path.isdir(studydir): 
        print "Directory {0} does not exist. Skipping.".format(studydir)
  
    if os.path.isfile(exam_tarball):  
        print "skipping (because {0} exists).".format(exam_tarball)
        continue
    

    print "processing."
    print "---"
    print "[{0}] Starting... ".format(datetime.datetime.now().isoformat(" "))

    if not os.path.exists(examdir): 
        print "Fetching DICOMS into {0}".format(examdir)
        logfile = "{0}/{1}.getdicom.log".format(LOGS_DIR,examdirname)
        if os.system("getdicom -d {examdir} {examid} > {logfile}".format(
            **vars())):
            print "Error getting exam {0} DICOMS.".format(examid)
            continue
        os.system("examinfo {0} | tee {1} > {2}/exam_info.txt".format(
            examid, examinfo, examdir))
        os.system("listseries11 {0} | tee -a {1} > {2}/exam_info.txt".format(
            examid, examinfo, examdir))

    # create tarfile and MD5sum
    print "Creating tar file of {0} as {1}".format(examdir, exam_tarball)
    tarcmd = "tar --remove-files -czf {0} -C {1} {2}".format(
        exam_tarball, studydir, examdirname)

    if os.system(tarcmd): 
        print "Error creating tarball {0}".format(exam_tarball)
        continue
    os.system('echo "md5sum: $(md5sum {0})" >> {1}'.format(
        exam_tarball, examinfo))

    # set group read permissions
    print "Setting correct permissions..."
    chmodcmd = "chmod -R u=rwX,g=rX,o= {0} {1}".format(exam_tarball, examinfo)

    if os.system(chmodcmd):
        print "Error setting exam permissions."
        continue

    print "[{0}] Finished. ".format(datetime.datetime.now().isoformat(" "))
    print "---\n"
