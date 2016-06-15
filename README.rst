This project is a tool to be used to manage the MR scanner data, and package it
for distribution to users. Specific features include: 

 - Pulls down all images available from the DICOM server on the scanner
 - Pulls down related pfiles
 - Renames files and folders to follow a naming convention
 - Stages all files for a scan in a working directory for admin inspection

Installation
------------

Dependencies: 
 - Python 2.x
 - [dcmtk](http://dcmtk.org)


I recommend using a conda environment to get set up::

    $ conda create -n mritool python
    $ source activate mritool 

Then clone this repo and setup::

	$ git clone git@github.com:TIGRLab/mritool.git
	$ cd mritool
	$ python setup.py install 

The install command will install some python dependencies.

Basic usage
-----------

The command line tool is `mritool`. Check the usage help via::

    $ mritool --help
    
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
    
    Commands: 
        pull                      Get an exam from the scanner
        check                     Check that an exam being processed has all of its files
        complete                  Mark an exam as complete by moving it to the processed folder
        list-exams                List all exams on the scanner
        list-series               List all series for the exam on the scanner
        list-inprocess            List the exams in the inprocess area
        sync-exams                Pulls all unpulled exams into the processing folder
        pfile-headers             Show the headers of a pfile
      
    Command options: 
        -b <bookingcode>          Booking code (StudyDescription)
        -d <date>                 Date (StudyDate)
        -e <exam>                 Exam number (StudyID)
        -o <outputdir>            Output directory (overrides --inprocess-dir)
        --bare                    Only pull dicom files
    
    Global options: 
        --inprocess-dir=<dir>     In-process exams directory [default: /data/mritooltest/InProcess]
        --processed-dir=<dir>     Processed exams directory [default: /data/mritooltest/Processed]
        --log-dir=<dir>           Logging directory [default: /data/mritooltest/logs]
        --host=<str>              Scanner hostname [default: CAMHMR]
        --port=<num>              Scanner port [default: 4006]
        --aet=<str>               Scanner AET [default: mr-srv1]
        --aec=<str>               Calling machine AEC [default: CAMHMR]
        -f, --force               Force a command, even if there are warnings.
        -v, --verbose             Verbose messaging.

--------- 

Known Issues
~~~~~~~~~~~~
- ``mritool sync-exams`` doesn't re-pull exams when they have been updated. See
  https://github.com/TIGRLab/mritool/issues/34. If ``sync`` has pulled an exam,
  and the exam is later updated, ``sync`` won't notice. You'll need to handle
  this situation by hand. 

Scanner data
~~~~~~~~~~~~

The GE scanner serves most data via a DICOM server which is accessible using
the gcmtk toolkit. pfiles (research scan data) are not accessible over DICOM transfer.

The GE scanner drops pfiles into the folder /export/home/signa/research/mrraw.
It keeps no record of them through the DICOM interface, so the files must be
scavanged from this folder. pfiles are named <id>.7, where <id> is reused after
a scanner restart (which happens daily). The upshot of this is that pfiles must
be pulled from the 'mrraw' folder at least daily, or else the may be
overwritten. 
