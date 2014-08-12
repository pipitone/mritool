# vim: expandtab ts=4 sw=4 tw=80: 
from mritools import mritools
import unittest

def test_get_pfile_info_nonexistant(): 
    pfile = "tests/does-not-exist"
    info = mritools.get_pfile_info(pfile)
    assert info is None

def test_get_pfile_info_invalid_pfile(): 
    pfile = "tests/test_pfiles.py"
    info = mritools.get_pfile_info(pfile)
    assert info is None

def test_get_pfile_info_valid_pfile(): 
    pfile = "tests/valid-pfile.7"
    info = mritools.get_pfile_info(pfile)
    assert info is not None
    assert info["exam_number"] == 2711
    assert info["exam_description"] == "Daily QA" 
    assert info["exam_type"] == "MR" 
    assert info["series_number"] == 6
    assert info["series_description"] == "AX FSPGR"

def test_get_pfile_info_valid_hos_pfile(): 
    pfile = "tests/valid-hos-pfile.7"
    info = mritools.get_pfile_info(pfile)
    assert info is not None
    assert info["exam_number"] == 2713
    assert info["exam_description"] == "ALCO1MR" 
    assert info["exam_type"] == "MR" 
    assert info["series_number"] == 4
    assert info["series_description"] == "HOS"

def tests_get_all_pfiles_info(): 
    root = "tests/"
    infos = mritools.get_all_pfiles_info(root)
    assert len(infos) == 2
    assert "tests/valid-hos-pfile.7" in infos
    assert "tests/valid-pfile.7" in infos
    assert infos["tests/valid-pfile.7"]["exam_number"] == 2711
