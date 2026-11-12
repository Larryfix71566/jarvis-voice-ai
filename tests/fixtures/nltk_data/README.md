# Offline English Punkt test resource

These four English punkt_tab text files are unchanged NLTK data, not generated
fixtures or a newly trained model. They match the sizes and SHA-256 pins already
approved in `sandbox/guest/prepare.sh`. Only the English resource used by the
locked NLTK/Pipecat test path is included; no pickle files or other languages.

Upstream: https://github.com/nltk/nltk_data/tree/gh-pages/packages/tokenizers
Archive: https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip
Archive size: 4,319,076 bytes.
Archive SHA-256: e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106
Author: Jan Strunk, as recorded by upstream punkt_tab.xml. The upstream model
README is retained beside the English directory, including training provenance
and the Kiss and Strunk (2006) citation. No additional license is asserted here.

`scripts/check_test_nltk_data.py` checks the exact English members and byte pins.
Its smoke mode uses only this resource and prohibits downloads/socket connects.
Pytest verifies and selects this directory before importing application modules;
CI selects it before the backend import smoke as well. No production tokenizer
path, sandbox preparation behavior, or user data is changed. New data/version
pins require a deliberate reviewed fixture update rather than an auto-download.
