PYTHON := .venv/bin/python
SCRIPTS := scripts

.PHONY: help run install-deps build-standalone build-onefile clean clean-build install uninstall uninstall-purge package-release aur-update

help:
	@echo "Targets:"
	@echo "  run              Run the app"
	@echo "  install-deps     Create venv and install dependencies"
	@echo "  build-standalone Build standalone binary"
	@echo "  build-onefile    Build onefile binary"
	@echo "  clean            Remove venv, build, and dist"
	@echo "  clean-build      Remove build artifacts only"
	@echo "  install          Install the built app system-wide"
	@echo "  uninstall        Remove the installed app"
	@echo "  uninstall-purge  Remove app + all data (settings, icons, cache)"
	@echo "  package-release  Build the GitHub release tarball"
	@echo "  aur-update       Update the AUR package from the latest release"

run: $(PYTHON)
	$(PYTHON) fila.py

install-deps:
	@bash $(SCRIPTS)/install-build-deps.sh

build-standalone: $(PYTHON)
	@bash $(SCRIPTS)/build-standalone.sh

build-onefile: $(PYTHON)
	@bash $(SCRIPTS)/build-onefile.sh

clean:
	rm -rf .venv build dist

clean-build:
	@bash $(SCRIPTS)/clean-build.sh

install:
	@bash ./install.sh

uninstall:
	@bash $(SCRIPTS)/uninstall.sh

uninstall-purge:
	@bash $(SCRIPTS)/uninstall.sh --purge

package-release: build-onefile
	@bash $(SCRIPTS)/package-release.sh $(VERSION)

aur-update:
	@bash $(SCRIPTS)/aur-update.sh $(VERSION)

$(PYTHON):
	$(MAKE) install-deps
