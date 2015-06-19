This project is a tool to be used to manage the MR scanner data, and package it
for distribution to users. Specific features include: 

 - Pulls down all images available from the DICOM server on the scanner
 - Pulls down spectroscopy and fMRI spiral scans
 - Renames files and folders to follow a naming convention
 - Stages all files for a scan in a working directory for admin inspection
 - Zips all scan files and places in a exam-specific folder

Installation
------------

I recommend using a conda environment to get set up::

    $ conda create -n mritool python
    $ source activate mritool 

Then clone this repo and setup::

	$ git clone git@github.com:TIGRLab/mritool.git
	$ cd mritool
	$ python setup.py install 

Basic usage
-----------

The command line tool is `mritool`. Check the usage help via::

    $ mritool --help

    Finds and copies exam data into a well-organized folder structure.
    
    Usage: 
        mritool [options] pull-exams [to <outputdir>] <exam_number>...
        mritool [options] pull-series [to <outputdir>] <exam_number> <series_number>
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
        --scans-dir=<dir>          Staging directory [default: ./output/processed]
        --staging-dir=<dir>        Staging directory [default: ./output/staging]
        --log-dir=<dir>            Logging directory [default: ./output/logs]
        --pfile-dir=<dir>          Pfile directory [default: /mnt/mrraw/camh]
        --host=<str>               Scanner hostname [default: CAMHMR]
        --port=<num>               Scanner port [default: 4006]
        --aet=<str>                Scanner AET [default: mr-srv1]
        --aec=<str>                Calling machine AEC [default: CAMHMR]
        -f, --force                Force a command, even if there are warnings.
        -n, --dry-run              Do nothing, but show what would be done. 
        -v, --verbose              Verbose messaging.

--------- 

Some design notes
-----------------

Scanner data
~~~~~~~~~~~~

The GE scanner serves most data via a DICOM server which is accessible using
the gcmtk toolkit. A few kinds of data are not accessible over DICOM transfer,
and those are: 

- spectroscopy scans (pfiles)
- spiral scans (pfiles) 
- fMRI reconstruction

These data must be retrieved separately from the scanner file system.

pfiles
~~~~~~

The GE scanner drops pfiles into the folder /export/home/signa/research/mrraw.
It keeps no record of them through the DICOM interface, so the files must be
scavanged from this folder. pfiles are named <id>.7, where <id> is reused after
a scanner restart (which happens daily). The upshot of this is that pfiles must
be pulled from the 'mrraw' folder at least daily, or else the may be
overwritten. 

Therefore, the following system has been devised: 

1. After a scan producing pfiles is complete, or before the end of the day, an
   MR tech will need to move the pfiles from the day into a safe storage location
   (/data/mrraw).  This is currently done using the `getmrraw` script, which:

   - creates a date stamped directory in /data/mrraw
   - finds *all* .7 and .physio files in the scanner's `mrraw` folder, and moves
     them to the this directory

2. Tech then runs the sort script 'sortfMRI5', which sorts Pfiles into "raw" spiral Pfiles, HOS Pfiles,
   and spectroscopy Pfiles. This sorting script also creates directories for fMRI files - and runs AFNI script
   to create the *.nii file. Original Pfiles are moved to a separate directory 'rawSprlioPfiles' for 
   short-term storage.

3. When the mritool is used to `pull` an exam, the `/data/mrraw` folder is
   scanned for matching pfiles, and those are copied into the staging area. 

DICOM Tools
~~~~~~~~~~~

Note: Server needs to have port 4006 open. 

Sunnybrook dcmtk-based tools: 
 - listexams11      : lists ALL the exams on the scanner (LONG!)
 - listseries11     : given an exam number, lists info on all of the series 
 - getdicom         : given an exam gets all all data, nicely named
 - getallseries11   : given an exam UID gets all series data
 - getseries11      : given an exam and series ID returns the data
 - mymovescu        : modified movescu (unsure exactly how)
 - getpfile         : untested        


e.g.::

    $ listexams11 | less                # pipe to less so you page through the results 
     
    $ listexams11 | grep ' 1550 '       # match the study ID, 1550
    67:   1550 |          | AP1334                     | MOAP025    ...
     
    $ listseries11 1550                 
    exam_uid:     1.2.840.113619.6.336.224574220444805981076681681360727924721
     
                   series #       description               images 
       series   1:   10                         3Plane Loc  (30 images)
       series   2: 20019                        Screen Save  (3 images)
       series   3: 1600                                 Ax  (169 images)
       series   4: 20018                        Screen Save  (3 images)
       series   5:    9                Obl Ax T2 DE FSE-XL  (90 images)
       series   6: 1603                               LTDC  (1 image)
       series   7:    7                  ASSET Calibration  (38 images)
       series   8:    8                        Ax DTI 60+5  (4810 images)
       series   9:   16                       Sag T1 BRAVO  (200 images)
       series  10:   19                     MRS - DLPFC Lt  (1 image)
       series  11:    1                         3Plane Loc  (30 images)
       series  12:   17                  ASSET Calibration  (38 images)
       series  13: 1601                                Cor  (182 images)
       series  14:   18                    MRS - sgACC B/L  (1 image)
    
    $ getdicom 1550
    
    $ getallseries11 -hier 1.2.840.113619.6.336.224574220444805981076681681360727924721
    #
    # use '-hier' option so that files get created in a hierarchy of folders
    # corresponding to the series IDs.  If you don't use this option, all of the
    # dicoms get spewed out into your current folder.
     
    
    $ bin/getseries11 1.2.840.113619.6.336.224574220444805981076681681360727924721 1
    #
    # This gets series #1 from the given exam. 


Notes on dcmtk tool usage
~~~~~~~~~~~~~~~~~~~~~~~~~

Querying the scanner:: 

  findscu -v              \ # verbose              
    -S                    \ # use database organised around studies
    -k 0008,0052="STUDY"  \ # query for the STUDY key
    -aec CAMHMR           \ # name of peer to call
    -aet mr-ftp           \ # title of peer who is calling
    CAMHMR 4006             # connection info: <host> <port>

Lines of output from the scanner are prepended with 'W: ', e.g.::

  W: # Dicom-Data-Set
  W: # Used TransferSyntax: Little Endian Explicit
  W: (0008,0005) CS [ISO_IR 100]                             #  10, 1 SpecificCharacterSet

