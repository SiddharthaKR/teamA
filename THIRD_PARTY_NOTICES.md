# Third-party reference data

| Data | Where | Source | License |
| --- | --- | --- | --- |
| JLPT vocabulary levels (primary) | `src/japanese_workplace_tutor/resources/jlpt_vocab_tanos_v1.json` | Jonathan Waller's JLPT lists, [tanos.co.uk](http://www.tanos.co.uk/jlpt/), as maintained in [jamsinclair/open-anki-jlpt-decks](https://github.com/jamsinclair/open-anki-jlpt-decks) | Data: CC BY (Jonathan Waller). Repository: MIT, Copyright (c) 2020 Jamie Sinclair |
| JLPT vocabulary levels (gap fill) | `openjlpt` package | [OpenJLPT](https://pypi.org/project/openjlpt/) 0.1.0 | CC BY-SA 4.0 |
| Tokenizer dictionary | `SudachiDict-core` package | [WorksApplications/SudachiDict](https://github.com/WorksApplications/SudachiDict) | Apache-2.0 |

Rebuild the tanos resource with `python scripts/build_jlpt_resource.py <folder with n1.csv .. n5.csv>`.

`business_vocab_v1.json`, `jlpt_overrides_v1.json` and `grammar_points_v1.json` are written by this project and are pending team review.
