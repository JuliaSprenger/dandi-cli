import os

BIDS_EXAMPLES_BLACKLIST = [
    "invalid_pet001",
]
BIDS_EXAMPLES_WHITELIST = [
    "asl003",
    "eeg_cbm",
    "hcp_example_bids",
    "micr_SEM",
    "micr_SEM-dandi",
    "micr_SPIM",
    "pet001",
    "pet003",
    "qmri_megre",
    "qmri_tb1tfl",
    "qmri_vfa",
]
TEST_SCHEMA_PATH = "{module_path}/support/bids/schemadata/1.7.0+012+dandi001"


def test__add_entity():
    from dandi.bids_validator_xs import _add_entity

    # Test empty input and directory creation and required entity
    regex_entities = ""
    entity = "subject"
    entity_shorthand = "sub"
    variable_field = "([a-z,A-Z,0-9]*?)"
    requirement_level = "required"

    _regex_entities = _add_entity(
        regex_entities,
        entity,
        entity_shorthand,
        variable_field,
        requirement_level,
    )

    assert _regex_entities == "sub-(?P=subject)"

    # Test append input and optional entity
    regex_entities = (
        "sub-(?P=subject)(|_ses-(?P=session))"
        "(|_task-(?P<task>([a-z,A-Z,0-9]*?)))(|_trc-(?P<tracer>([a-z,A-Z,0-9]*?)))"
        "(|_rec-(?P<reconstruction>([a-z,A-Z,0-9]*?)))"
        "(|_run-(?P<run>([a-z,A-Z,0-9]*?)))"
    )
    entity = "recording"
    entity_shorthand = "recording"
    variable_field = "([a-z,A-Z,0-9]*?)"
    requirement_level = "optional"

    _regex_entities = _add_entity(
        regex_entities,
        entity,
        entity_shorthand,
        variable_field,
        requirement_level,
    )

    assert (
        _regex_entities == "sub-(?P=subject)(|_ses-(?P=session))"
        "(|_task-(?P<task>([a-z,A-Z,0-9]*?)))(|_trc-(?P<tracer>([a-z,A-Z,0-9]*?)))"
        "(|_rec-(?P<reconstruction>([a-z,A-Z,0-9]*?)))"
        "(|_run-(?P<run>([a-z,A-Z,0-9]*?)))"
        "(|_recording-(?P<recording>([a-z,A-Z,0-9]*?)))"
    )


def test__add_extensions():
    from dandi.bids_validator_xs import _add_extensions

    # Test single extension
    regex_string = (
        "sub-(?P=subject)(|_ses-(?P=session))"
        "_sample-(?P<sample>([a-z,A-Z,0-9]*?))"
        "(|_acq-(?P<acquisition>([a-z,A-Z,0-9]*?)))_photo"
    )
    variant = {
        "suffixes": ["photo"],
        "extensions": [".jpg"],
        "entities": {
            "subject": "required",
            "session": "optional",
            "sample": "required",
            "acquisition": "optional",
        },
    }
    _regex_string = _add_extensions(regex_string, variant)

    assert (
        _regex_string == "sub-(?P=subject)(|_ses-(?P=session))"
        "_sample-(?P<sample>([a-z,A-Z,0-9]*?))"
        "(|_acq-(?P<acquisition>([a-z,A-Z,0-9]*?)))_photo\\.jpg"
    )

    # Test multiple extensions
    regex_string = (
        "sub-(?P=subject)(|_ses-(?P=session))"
        "_sample-(?P<sample>([a-z,A-Z,0-9]*?))"
        "(|_acq-(?P<acquisition>([a-z,A-Z,0-9]*?)))_photo"
    )
    variant = {
        "suffixes": ["photo"],
        "extensions": [".jpg", ".png", ".tif"],
        "entities": {
            "subject": "required",
            "session": "optional",
            "sample": "required",
            "acquisition": "optional",
        },
    }
    _regex_string = _add_extensions(regex_string, variant)

    assert (
        _regex_string == "sub-(?P=subject)(|_ses-(?P=session))"
        "_sample-(?P<sample>([a-z,A-Z,0-9]*?))"
        "(|_acq-(?P<acquisition>([a-z,A-Z,0-9]*?)))"
        "_photo(\\.jpg|\\.png|\\.tif)"
    )


def test__add_subdirs():
    from dandi.bids_validator_xs import _add_subdirs

    regex_string = "sub-(?P=subject)_sessions\\.(tsv|json)"
    variant = {
        "suffixes": ["sessions"],
        "extensions": [".tsv", ".json"],
        "entities": {"subject": "required"},
    }
    datatype = "tabular_metadata"
    entity_definitions = {
        "acquisition": {
            "name": "Acquisition",
            "entity": "acq",
            "type": "string",
            "format": "label",
        },
        "session": {
            "name": "Session",
            "entity": "ses",
            "type": "string",
            "format": "label",
        },
        "subject": {
            "name": "Subject",
            "entity": "sub",
            "type": "string",
            "format": "label",
        },
    }
    modality_datatypes = [
        "anat",
        "dwi",
        "fmap",
        "func",
        "perf",
        "eeg",
        "ieeg",
        "meg",
        "beh",
        "pet",
        "micr",
    ]
    _regex_string = _add_subdirs(
        regex_string, variant, datatype, entity_definitions, modality_datatypes
    )

    assert (
        _regex_string == "/sub-(?P<subject>([a-z,A-Z,0-9]*?))/sub-(?P=subject)"
        "_sessions\\.(tsv|json)"
    )


def test__add_suffixes():
    from dandi.bids_validator_xs import _add_suffixes

    # Test single expansion
    regex_entities = "sub-(?P=subject)"
    variant = {
        "suffixes": ["sessions"],
        "extensions": [
            ".tsv",
            ".json",
        ],
        "entities": {"subject": "required"},
    }
    regex_string = "sub-(?P=subject)_sessions"

    _regex_string = _add_suffixes(regex_entities, variant)

    assert _regex_string == regex_string

    # Test multiple expansions
    regex_entities = (
        "sub-(?P=subject)(|_ses-(?P=session))"
        "(|_acq-(?P<acquisition>([a-z,A-Z,0-9]*?)))"
        "(|_rec-(?P<reconstruction>([a-z,A-Z,0-9]*?)))"
        "(|_dir-(?P<direction>([a-z,A-Z,0-9]*?)))(|_run-(?P<run>([a-z,A-Z,0-9]*?)))"
        "(|_recording-(?P<recording>([a-z,A-Z,0-9]*?)))"
    )
    variant = {
        "suffixes": [
            "physio",
            "stim",
        ],
        "extensions": [
            ".tsv.gz",
            ".json",
        ],
        "entities": {
            "subject": "required",
            "session": "optional",
            "acquisition": "optional",
            "reconstruction": "optional",
            "direction": "optional",
            "run": "optional",
            "recording": "optional",
        },
    }
    regex_string = (
        "sub-(?P=subject)(|_ses-(?P=session))"
        "(|_acq-(?P<acquisition>([a-z,A-Z,0-9]*?)))"
        "(|_rec-(?P<reconstruction>([a-z,A-Z,0-9]*?)))"
        "(|_dir-(?P<direction>([a-z,A-Z,0-9]*?)))(|_run-(?P<run>([a-z,A-Z,0-9]*?)))"
        "(|_recording-(?P<recording>([a-z,A-Z,0-9]*?)))"
        "_(physio|stim)"
    )

    _regex_string = _add_suffixes(regex_entities, variant)

    assert _regex_string == regex_string


def test_load_all():
    from dandi.bids_validator_xs import load_all

    schema_path = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        "../support/bids/schemadata/1.7.0+012+dandi001",
    )
    schema_all = load_all(schema_path)

    # Check if expected keys are present in all entries
    for entry in schema_all:
        assert "regex" in list(entry.keys())
        assert "mandatory" in list(entry.keys())


def test_write_report(tmp_path):
    from dandi.bids_validator_xs import write_report

    validation_result = {}

    validation_result["schema_tracking"] = [
        {
            "regex": ".*?/sub-(?P<subject>([a-z,A-Z,0-9]*?))/"
            "(|ses-(?P<session>([a-z,A-Z,0-9]*?))/)anat/sub-(?P=subject)"
            "(|_ses-(?P=session))(|_acq-(?P<acquisition>([a-z,A-Z,0-9]*?)))"
            "(|_ce-(?P<ceagent>([a-z,A-Z,0-9]*?)))"
            "(|_rec-(?P<reconstruction>([a-z,A-Z,0-9]*?)))"
            "(|_run-(?P<run>([a-z,A-Z,0-9]*?)))"
            "(|_part-(?P<part>(mag|phase|real|imag)))"
            "_(T1w|T2w|PDw|T2starw|FLAIR|inplaneT1|inplaneT2|PDT2|angio|T2star)"
            "\\.(nii.gz|nii|json)$",
            "mandatory": False,
        }
    ]
    validation_result["schema_listing"] = [
        {
            "regex": ".*?/sub-(?P<subject>([a-z,A-Z,0-9]*?))/"
            "(|ses-(?P<session>([a-z,A-Z,0-9]*?))/)anat/sub-(?P=subject)"
            "(|_ses-(?P=session))(|_acq-(?P<acquisition>([a-z,A-Z,0-9]*?)))"
            "(|_ce-(?P<ceagent>([a-z,A-Z,0-9]*?)))"
            "(|_rec-(?P<reconstruction>([a-z,A-Z,0-9]*?)))"
            "(|_run-(?P<run>([a-z,A-Z,0-9]*?)))"
            "(|_part-(?P<part>(mag|phase|real|imag)))"
            "_(T1w|T2w|PDw|T2starw|FLAIR|inplaneT1|inplaneT2|PDT2|angio|T2star)"
            "\\.(nii.gz|nii|json)$",
            "mandatory": False,
        }
    ]
    validation_result["path_tracking"] = [
        "/home/chymera/.data2/datalad/000026/"
        "rawdata/sub-EXC022/anat/sub-EXC022_ses-MRI_flip-1_VFA.nii.gz"
    ]
    validation_result["path_listing"] = [
        "/home/chymera/.data2/datalad/000026/"
        "rawdata/sub-EXC022/anat/sub-EXC022_ses-MRI_flip-1_VFA.nii.gz"
    ]

    report_path = os.path.join(
        tmp_path,
        "output_bids_validator_xs_write.log",
    )
    expected_report_path = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        "data/expected_bids_validator_xs_write.log",
    )
    write_report(validation_result, report_path=report_path)
    with open(report_path, "r") as f:
        report_text = f.read()
    with open(expected_report_path, "r") as f:
        expected_report_text = f.read()
    assert report_text == expected_report_text


def test_bids_datasets(bids_examples):
    from dandi.bids_validator_xs import validate_bids

    # Validate per dataset, with automatic schema selection:
    for i in os.listdir(bids_examples):
        if i in BIDS_EXAMPLES_WHITELIST:
            result = validate_bids(
                os.path.join(bids_examples, i),
            )
            # Have all files been validated?
            assert len(result["path_tracking"]) == 0


def test_error_datasets(bids_examples):
    from dandi.bids_validator_xs import validate_bids

    # Validate per dataset, with automatic schema selection:
    for i in os.listdir(bids_examples):
        if i in BIDS_EXAMPLES_BLACKLIST:
            result = validate_bids(
                os.path.join(bids_examples, i),
            )
            # Are there non-validated files?
            assert len(result["path_tracking"]) != 0


def test_bids_datasets_selected_paths(bids_examples, tmp_path):
    from dandi.bids_validator_xs import validate_bids

    # Create input for file list based validation
    selected_dir = os.path.join(bids_examples, BIDS_EXAMPLES_WHITELIST[0])
    selected_paths = []
    for root, dirs, files in os.walk(selected_dir, topdown=False):
        for f in files:
            selected_path = os.path.join(root, f)
            selected_paths.append(selected_path)
    # Does explicit schema specification work?
    result = validate_bids(selected_paths, schema_version=TEST_SCHEMA_PATH)

    # Does terminal debug output work?
    result = validate_bids(selected_paths, debug=True)

    # Does the default report path work?
    result = validate_bids(selected_paths, report_path=True)

    # Does custom report path specification work?
    result = validate_bids(
        selected_paths,
        schema_version=TEST_SCHEMA_PATH,
        report_path=os.path.join(tmp_path, "test_bids.log"),
    )
    # Have all files been validated?
    assert len(result["path_tracking"]) == 0
