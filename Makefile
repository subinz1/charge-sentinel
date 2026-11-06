UUID := charge-sentinel@subinz1.github.io
NAME := charge-sentinel
VERSION := 0.1.0
SCHEMA := schemas/org.gnome.shell.extensions.charge-sentinel.gschema.xml
DIST := dist
RPM_TOPDIR := $(abspath build/rpmbuild)
RPM_SOURCE := $(RPM_TOPDIR)/SOURCES/$(NAME)-$(VERSION).tar.gz

.PHONY: validate test package rpm-source rpm clean

validate:
	glib-compile-schemas --strict --dry-run schemas
	python3 -m py_compile src/charge-sentinel-helper.py src/charge-sentinel-capabilities.py src/charge-sentinel-doctor.py src/charge_sentinel_capabilities.py
	python3 -m unittest discover -s tests -v

test:
	python3 -m unittest discover -s tests -v

package: validate
	mkdir -p $(DIST)
	gnome-extensions pack --force --out-dir $(DIST) --schema $(SCHEMA) .

rpm-source:
	mkdir -p $(RPM_TOPDIR)/SOURCES
	git archive --format=tar.gz --prefix=$(NAME)-$(VERSION)/ --output=$(RPM_SOURCE) HEAD

rpm: validate rpm-source
	rpmbuild --define "_topdir $(RPM_TOPDIR)" -ba packaging/fedora/$(NAME).spec

clean:
	rm -rf $(DIST) build
