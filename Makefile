UUID := charge-sentinel@subinz1.github.io
SCHEMA := schemas/org.gnome.shell.extensions.charge-sentinel.gschema.xml
DIST := dist

.PHONY: validate test package clean

validate:
	glib-compile-schemas --strict --dry-run schemas
	python3 -m py_compile src/charge-sentinel-helper.py
	python3 -m unittest discover -s tests -v

test:
	python3 -m unittest discover -s tests -v

package: validate
	mkdir -p $(DIST)
	gnome-extensions pack --force --out-dir $(DIST) --schema $(SCHEMA) .

clean:
	rm -rf $(DIST)
