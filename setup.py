from setuptools import setup

setup(name='mritool',
      version='0.1',
      description='A tool for managing GE scanner data for the CAMH MR Unit',
      url='http://github.com/TIGRLab/mritool',
      author='Jon Pipitone',
      author_email='jon@pipitone.ca',
      license='MIT',
      packages=['mritool'],
      install_requires = [
		'docopt', 
		'tabulate',
		'pydicom', 
		'pfile_tools'],
	  test_suite = 'nose.collector', 
      tests_require=['nose'],	
	  entry_points = {
		'console_scripts' : [ 'mritool = mritool.command_line:main' ],
	  },
	  data_files = [ 
		('/etc/bash_completion.d', ['mritool.sh']), 
	  ],
      zip_safe=False)
