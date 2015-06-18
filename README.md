This project is a tool to be used to manage the MR scanner data, and package it
for distribution to users. Specific features include: 

 - Pulls down all images available from the DICOM server on the scanner
 - Pulls down spectroscopy and fMRI spiral scans
 - Renames files and folders to follow a naming convention
 - Stages all files for a scan in a working directory for admin inspection
 - Zips all scan files and places in a exam-specific folder

## Installation

I recommend using a conda environment to get set up: 

	$ conda create -n mritool python
    $ source activate mritool 

Then clone this repo and setup: 

	$ git clone git@github.com:TIGRLab/mritool.git
	$ cd mritool
	$ python setup.py install 

## Basic usage

The command line tool is `mritool`. Check the usage help via: 

	$ mritool --help
