from setuptools import setup

setup(name='mritool',
      version='0.1',
      description='A tool for managing GE scanner data for the CAMH MR Unit',
      url='http://github.com/TIGRLab/mritool',
      author='Jon Pipitone',
      author_email='jon@pipitone.ca',
      license='MIT',
      packages=['mritools'],
      install_requires = [
		'docopt', 
		'tabulate',
		'pydicom', 
		'pfile_tools'],
	  test_suite = 'nose.collector', 
      tests_require=['nose'],	
	  entry_points = {
		'console_scripts' : [ 'mritool = mritools.command_line:main' ],
	  },
      zip_safe=False)
