help:
	@echo  'Commands:'
	@echo  '  autoformat   - Run black on all the source files, to format them automatically'
	@echo  '  verify       - Run a bunch of checks, to see if there are any obvious deficiencies in the code'
	@echo  ''

autoformat:
	black *.py

verify:
	flake8 --config=.flake8 *.py
	pylint --rcfile=.pylintrc *.py
	bandit *.py