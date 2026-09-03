# bmc-toolkit

Claude Code plugin for BMC firmware developers.

The first skill, `bmc-spec`, answers questions about BMC specifications
(IPMI, DCMI, DMTF MCTP / PLDM / SPDM / NC-SI / SMBIOS, Redfish, NVMe and
NVMe-MI, OCP DC-SCM and DC-MHS, I2C, SMBus, CMIS) and about OpenBMC source
code. It keeps a local library of the documents and repositories you have
asked about, defaults to the latest published version of each document,
serves any specific version on request, and cites document, version, section
and page in every answer.

**Status: pre-release.** The repository holds the plugin skeleton; the
library, fetching, extraction and answering workflow are being added
milestone by milestone.

## Install

```
/plugin marketplace add ianmhuang/bmc-toolkit
/plugin install bmc-toolkit@bmc-toolkit
```

Requirements: Python 3.11 or newer on `PATH` as `python` or `python3`, and
`git`. Third-party packages listed in `requirements.txt` are installed once
into the plugin's data directory by a `SessionStart` hook; in a development
checkout run `pip install -r requirements.txt` yourself.

## Library location

Documents and code checkouts live under `~/.bmc-specs/` by default. Set
`BMC_SPEC_LIBRARY` to move it. The path is shared by every project on the
machine.

## Development

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

## License

MIT. The specifications the tool downloads remain under their publishers'
licences and are never redistributed with this repository.
