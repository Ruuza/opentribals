#! /usr/bin/env bash
set -e
set -x

export ENVIRONMENT=test

python app/backend_pre_start.py

bash scripts/test.sh "$@"
