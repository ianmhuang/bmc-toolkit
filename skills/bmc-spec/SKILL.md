---
name: bmc-spec
description: Answer questions about BMC specifications (IPMI, DCMI, DMTF MCTP/PLDM/SPDM/NC-SI/SMBIOS, Redfish, NVMe/NVMe-MI, OCP DC-SCM/DC-MHS, I2C, SMBus, CMIS) and about OpenBMC source code, citing document, version, section and page. Use whenever the user asks what a spec says, how a command or field is defined, or how OpenBMC implements something.
allowed-tools: Bash(python *)
---

# bmc-spec

Status: skeleton. The answering workflow arrives in a later milestone; this
file currently only exposes the helper CLI so the plugin can be installed and
smoke-tested.

## Helper CLI

Every operation goes through one launcher:

```
python "${CLAUDE_SKILL_DIR}/scripts/bmcspec.py" --help
python "${CLAUDE_SKILL_DIR}/scripts/bmcspec.py" library
```

`library` prints the Library path (the on-disk store of specifications and
code trees): `$BMC_SPEC_LIBRARY` when set, otherwise `~/.bmc-specs`. Tell the
user this path the first time the Library is created in a session.
