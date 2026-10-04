#!/usr/bin/env bash
set -e
rasa data validate --fail-on-warnings
rasa data split nlu --training-fraction 0.8 --out train_test_split
rasa train
rasa test nlu --nlu train_test_split/test_data.yml --out results/nlu
rasa test nlu --nlu data/nlu.yml --cross-validation --folds 5 --out results/cv
rasa test core --stories tests/test_stories.yml --out results/core
pytest -q
