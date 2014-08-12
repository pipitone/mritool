# vim: expandtab ts=4 sw=4 tw=80: 
from mritools import mritools
import unittest

def test_get_pfile_info_nonexistant(): 
    path = "tests/does-not-exist"
    pfile = mritools.get_pfile_info(path)
    assert pfile is None

def test_get_pfile_info_invalid_pfile(): 
    path = "tests/test_pfiles.py"
    pfile = mritools.get_pfile_info(path)
    assert pfile is None

def test_get_pfile_info_valid_pfile(): 
    path = "tests/valid-pfile.7"
    pfile = mritools.get_pfile_info(path)
    assert pfile is not None
    assert pfile.path == path
    assert pfile.headers["exam_number"] == 2711
    assert pfile.headers["exam_description"] == "Daily QA" 
    assert pfile.headers["exam_type"] == "MR" 
    assert pfile.headers["series_number"] == 6
    assert pfile.headers["series_description"] == "AX FSPGR"

def test_get_pfile_info_valid_hos_pfile(): 
    path = "tests/valid-hos-pfile.7"
    pfile = mritools.get_pfile_info(path)
    assert pfile is not None
    assert pfile.path == path
    assert pfile.headers["exam_number"] == 2713
    assert pfile.headers["exam_description"] == "ALCO1MR" 
    assert pfile.headers["exam_type"] == "MR" 
    assert pfile.headers["series_number"] == 4
    assert pfile.headers["series_description"] == "HOS"

def tests_get_all_pfiles_info(): 
    root = "tests/"
    pfiles = mritools.get_all_pfiles_info(root)
    assert len(pfiles) == 2
    assert "tests/valid-hos-pfile.7" in pfiles
    assert "tests/valid-pfile.7" in pfiles
    assert pfiles["tests/valid-pfile.7"].headers["exam_number"] == 2711
    assert pfiles["tests/valid-pfile.7"].path == "tests/valid-pfile.7"
