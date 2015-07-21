.PHONY: build
build: 
	docopt-completion mritool --manual-bash
	mv mritool.sh autocomplete.sh
