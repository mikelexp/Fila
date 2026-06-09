python := 'venv/bin/python'
scripts := 'scripts'

default:
    @just --list

help:
    @just --list

run: _ensure-python
    {{python}} fila.py

install-deps:
    bash {{scripts}}/install-build-deps.sh

build-standalone: _ensure-python
    bash {{scripts}}/build-standalone.sh

build-onefile: _ensure-python
    bash {{scripts}}/build-onefile.sh

clean:
    rm -rf venv build dist

clean-build:
    bash {{scripts}}/clean-build.sh

install:
    bash ./install.sh

uninstall:
    bash {{scripts}}/uninstall.sh

uninstall-purge:
    bash {{scripts}}/uninstall.sh --purge

package-release VERSION='': build-onefile
    bash {{scripts}}/package-release.sh "{{VERSION}}"

aur-update VERSION='':
    bash {{scripts}}/aur-update.sh "{{VERSION}}"

_ensure-python:
    @if [ ! -f '{{python}}' ]; then just install-deps; fi
