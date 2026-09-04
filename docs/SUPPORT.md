# Support Level

What the tool can tell you about the documents in the Source Catalog:
one table per family, generated from `bmc_toolkit/spec/catalog.toml` and
`docs/golden-questions.md`, never edited by hand. Documents marked
`unlisted` in the catalog are left out; `catalog` prints the full list.

- **Document**: the catalog id (what you pass to `fetch`, `find`, `page`
  and the other commands) and the document's title.
- **Access**: `open` (the tool downloads it), `gated` (free registration or
  a request to the publisher), `member`, `confidential` (NDA). `open
  (latest gated)` means the newest version sits behind a registration:
  `fetch DOC` refuses it and names the newest open one (`--version X`);
  `fetch --all` takes that one.
- **Latest**: the newest published version the catalog lists; `-` when a
  manual document lists none.
- **Verified**: `PASS` when the document has been checked against the
  acceptance questions in `docs/golden-questions.md` (that file names the
  questions and the version each was checked on), `-` otherwise. Every
  open document is `PASS`.
- **Known limit**: what the document's PDF does not allow (tables drawn as
  images, bookmarks that are not headings, a defective text layer) and
  which command to use instead.

To regenerate, run the command below and replace everything after the
marker line with its output:

```
python skills/bmc-spec/scripts/bmcspec.py catalog --table --by-family --golden docs/golden-questions.md
```

<!-- generated below: catalog --table --by-family --golden docs/golden-questions.md -->

## IPMI, IPMB, FRU and DCMI

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `IPMI` Intelligent Platform Management Interface Specification, Second Generation, v2.0 | open | 2.0 rev 1.1 | PASS | Table numbers are missing from the PDF's text layer; tables are cited by title. |
| `IPMI-UPDATE` IPMI Specification, Second Generation, v2.0 Specification Update (Errata/Addenda/Clarifications) | open | 2.0 rev 1.1 Errata 7 | PASS | - |
| `IPMB` Intelligent Platform Management Bus Communications Protocol Specification | open | 1.0 | PASS | PDF bookmarks carry titles without section numbers: section by title, not by number. |
| `IPMI-FRU` Platform Management FRU Information Storage Definition | open | 1.0 rev 1.3 | PASS | - |
| `DCMI` Data Center Manageability Interface Specification | open | 1.5 | PASS | - |

## Enhanced Serial Peripheral Interface

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `ESPI` Enhanced Serial Peripheral Interface (eSPI) Base Specification | open | 1.6 | PASS | - |

## Management Component Transport Protocol

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `DSP0236` Management Component Transport Protocol (MCTP) Base Specification | open | 1.3.3 | PASS | - |
| `DSP0237` Management Component Transport Protocol (MCTP) SMBus/I2C Transport Binding Specification | open | 1.2.0 | PASS | PDF bookmarks are cross-reference anchors, not headings: section finds nothing and cites name an anchor; use find and page. |
| `DSP0238` Management Component Transport Protocol (MCTP) PCIe® VDM Transport Binding Specification | open | 1.4.0 | PASS | - |
| `DSP0239` Management Component Transport Protocol (MCTP) IDs and Codes Specification | open | 1.12.0 | PASS | One page holds an emoji that breaks pdfium's character order; extracted without layout. |
| `DSP0233` Management Component Transport Protocol (MCTP) I3C Transport Binding Specification | open | 1.0.1 | PASS | - |
| `DSP0253` MCTP Serial Transport Binding Specification | open | 1.0.0 | PASS | Some PDF bookmarks are cross-reference anchors; a cite may name one instead of the heading. |
| `DSP0254` MCTP KCS Transport Binding Specification | open | 1.0.0 | PASS | Some PDF bookmarks are cross-reference anchors; a cite may name one instead of the heading. |
| `DSP0256` Management Component Transport Protocol (MCTP) Host Interface Specification | open | 2.0.0 | PASS | - |
| `DSP0283` Management Component Transport Protocol (MCTP) Universal Serial Bus (USB) Transport Binding Specification | open | 1.1.0 | PASS | - |
| `DSP0284` Management Component Transport Protocol (MCTP) Memory-Mapped Buffer Interface (MMBI) Transport Binding Specification | open | 1.0.1 | PASS | PDF bookmarks are cross-reference anchors as well as headings: section 5.2 is found, but a page cite can name the anchor before the heading (page 10 cites 5.1.3 for section 5.2); check the heading in the page text. Figure 1's rotated labels extract as single letters; use render. |
| `DSP0292` Management Component Transport Protocol (MCTP) PCC Transport Binding Specification | open | 1.0.0 | PASS | - |
| `DSP0235` NVMe™ (NVMe Express™) Management Messages over MCTP Binding Specification | open | 1.0.1 | PASS | PDF bookmarks are cross-reference anchors, not headings: section finds nothing and cites name an anchor; use find and page. |
| `DSP0234` CXL™ Fabric Manager API over MCTP Binding Specification | open | 1.0.0 | PASS | PDF bookmarks are cross-reference anchors, not headings: section finds nothing and cites name an anchor; use find and page. |
| `DSP0281` CXL™ Type 3 Device Component Command Interface over MCTP Binding Specification | open | 1.0.0 | PASS | - |
| `DSP0291` PCIe® Management Interface (PCIe-MI®) over MCTP Binding Specification | open | 1.0.0 | PASS | - |

## Platform Level Data Model

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `DSP0240` Platform Level Data Model (PLDM) Base Specification | open | 1.1.1 | PASS | - |
| `DSP0241` Platform Level Data Model (PLDM) Over MCTP Binding Specification | open | 1.0.0 | PASS | - |
| `DSP0242` Platform Level Data Model (PLDM) for File Transfer Specification | open | 1.0.1 | PASS | - |
| `DSP0245` Platform Level Data Model (PLDM) IDs and Codes Specification | open | 1.4.0 | PASS | - |
| `DSP0246` Platform Level Data Model (PLDM) for SMBIOS Transfer Specification | open | 1.0.1 | PASS | - |
| `DSP0247` Platform Level Data Model (PLDM) for BIOS Control and Configuration Specification | open | 1.0.0 | PASS | - |
| `DSP0248` PLDM Platform Monitoring and Control Specification | open | 1.3.1 | PASS | - |
| `DSP0249` Platform Level Data Model (PLDM) State Set Specification | open | 1.4.0 | PASS | - |
| `DSP0257` Platform Level Data Model (PLDM) for FRU Data Specification | open | 2.0.0 | PASS | - |
| `DSP0267` Platform Level Data Model (PLDM) for Firmware Update Specification | open | 1.3.0 | PASS | - |
| `DSP0218` Platform Level Data Model (PLDM) for Redfish Device Enablement | open | 1.2.0 | PASS | - |

## Security Protocol and Data Model

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `DSP0274` Security Protocol and Data Model (SPDM) Specification | open | 1.4.1 | PASS | Most tables have no ruling lines; they are drawn as cell boxes, which table reads (the table: line says cells). |
| `DSP0275` Security Protocol and Data Model (SPDM) over MCTP Binding Specification | open | 1.0.2 | PASS | - |
| `DSP0276` Secured Messages using SPDM over MCTP Binding Specification | open | 2.0.0 | PASS | - |
| `DSP0277` Secured Messages Using SPDM Specification | open | 2.0.0 | PASS | - |
| `DSP0286` Security Protocol and Data Model (SPDM) to Storage Binding Specification | open | 1.0.0 | PASS | - |
| `DSP0287` SPDM over TCP Binding Specification | open | 1.0.0 | PASS | - |
| `DSP0289` Security Protocol and Data Model (SPDM) Authorization Specification | open | 1.0.0 | PASS | - |

## Network Controller Sideband Interface

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `DSP0222` Network Controller Sideband Interface (NC-SI) Specification | open | 1.2.1 | PASS | - |
| `DSP0261` NC-SI over MCTP Binding Specification | open | 1.3.1 | PASS | - |
| `DSP0296` Network Controller Sideband Interface (NC‐SI) over Ethernet over USB Binding Specification | open | 1.0.0 | PASS | - |

## System Management BIOS

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `DSP0134` SMBIOS Specification | open | 3.9.0 | PASS | - |

## Redfish

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `DSP0266` Redfish Specification | open | 1.24.0 | PASS | - |
| `DSP8010` Redfish Schema Bundle | open | 2026.1 | PASS | - |
| `DSP0268` Redfish Data Model Specification | open | 2026.1 | PASS | - |
| `DSP2046` Redfish Resource and Schema Guide | open | 2026.1 | PASS | - |
| `DSP0270` Redfish Host Interface Specification | open | 1.3.1 | PASS | - |
| `DSP0272` Redfish Interoperability Profiles Specification | open | 1.10.0 | PASS | - |
| `DSP2053` Redfish Property Guide | open | 2026.1 | PASS | The whole guide is one property table over 300-odd pages: table prints the rows that start on the asked page and says so (--all-rows prints every row). |
| `DSP2065` Redfish Message Registry Guide | open | 2026.1 | PASS | - |
| `DSP8011` Redfish Standard Registries Bundle | open | 2026.1 | PASS | ZIP of registries: registry reads the message registries (newest file per registry); the privilege registries, the HTML and the PDF stay in the archive (DSP2065 is the PDF's own catalog entry). |
| `DSP8013` Redfish Interoperability Profiles Bundle | open | 2026.1 | PASS | ZIP of profiles: schema reads the profile schema (RedfishInteroperabilityProfile); the bundle holds no profile documents, and its PDF stays in the archive (DSP0272 is the PDF's own catalog entry). |

## NVM Express

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `NVME-BASE` NVM Express Base Specification | open | 2.4 | PASS | - |
| `NVME-MI` NVM Express Management Interface Specification | open | 2.2 | PASS | - |
| `NVME-PCIE` NVM Express over PCIe Transport Specification | open | 1.4 | PASS | - |

## OCP Datacenter-ready Secure Control Module

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `DC-SCM` Datacenter-ready Secure Control Module (DC-SCM) Specification | open | Rev 2.2 Ver 1.0 | PASS | Tables are images: use page and render; table finds nothing on those pages. |
| `LTPI` DC-SCM LVDS Tunneling Protocol and Interface (LTPI) Specification | open | Rev 1.2 Ver 1.0 | PASS | - |

## OCP Datacenter Modular Hardware System

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `M-CRPS` DC-MHS Modular Hardware System Common Redundant Power Supply (M-CRPS) Base Specification | open | R1 v1.0 RC4 | PASS | - |
| `M-PIC` DC-MHS Platform Infrastructure Connectivity (M-PIC) Specification | open | R1 v1.11 | PASS | - |
| `M-XIO` DC-MHS Extensible I/O (M-XIO) Specification | open | R1 v1.04 RC1 | PASS | - |
| `M-DNO` DC-MHS Densified Node Operation (M-DNO) Specification | open | R1 v1.1 RC2 | PASS | - |
| `M-FLW` DC-MHS Full Width HPM (M-FLW) Specification | open | R1 v1.2 RC3 | PASS | - |
| `M-PESTI` DC-MHS Peripheral Sideband Tunneling Interface (M-PESTI) Specification | open | R1 v1.2 RC2 | PASS | - |
| `M-SDNO` DC-MHS Shared-Infrastructure Densified Node Operation (M-SDNO) Specification | open | v1.1 RC2 | PASS | - |

## I2C bus

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `UM10204` I2C-bus specification and user manual (UM10204) | open | Rev. 7.0 | PASS | - |

## System Management Bus

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `SMBUS` System Management Bus (SMBus) Specification | open | 3.3.1 | PASS | - |

## Common Management Interface Specification (optical modules)

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `CMIS` Common Management Interface Specification (OIF-CMIS) | open | 5.4 | PASS | Tables have no ruling lines on a few pages; those are drawn as cell boxes, which table reads (the table: line says cells). |

## Low Pin Count interface

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `LPC` Low Pin Count (LPC) Interface Specification | open | 1.1 | PASS | - |

## PWM fan control

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `PWM-FAN` 4-Wire Pulse Width Modulation (PWM) Controlled Fans Specification | open | Rev 1.3 | PASS | - |

## SFF specifications (SGPIO, module EEPROMs)

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `SFF-8485` SFF-8485 Specification for Serial GPIO (SGPIO) Bus | open | Rev 0.7 | PASS | - |
| `SFF-8472` SFF-8472 Specification for Management Interface for SFP+ | open | Rev 12.5a | PASS | - |
| `SFF-8636` SFF-8636 Specification for Management Interface for 4-lane Modules and Cables | open | Rev 2.12 | PASS | - |
| `SFF-8024` SFF-8024 Specification for SFF Module Management Reference Code Tables | open | Rev 4.14 | PASS | - |

## Power Management Bus

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `PMBUS-I` PMBus Power System Management Protocol Specification Part I: General Requirements, Transport and Electrical Interface | open (latest gated) | 1.5 | PASS | - |
| `PMBUS-II` PMBus Power System Management Protocol Specification Part II: Command Language | open (latest gated) | 1.5 | PASS | - |

## OCP Security (root of trust, attestation)

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `CALIPTRA` Caliptra: A Datacenter System on a Chip (SoC) Root of Trust (RoT) Modular Base Specification | open | 2.0 | PASS | - |
| `OCP-ATTEST` Attestation of System Components v1.0: Requirements and Recommendations | open | 1.0 | PASS | The PDF has no bookmarks and no contents page: section finds nothing; use find and page. |

## OCP NIC 3.0

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `OCP-NIC` OCP NIC 3.0 Design Specification | open | 1.6.0 | PASS | The document is line-numbered; page text carries the numbers, so a find hit may start with the line number. |

## Trusted Computing Group (TPM 2.0, PC Client firmware profile, DICE)

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `TPM2-P0` Trusted Platform Module 2.0 Library Part 0: Introduction | open | 185 | PASS | - |
| `TPM2-P1` Trusted Platform Module 2.0 Library Part 1: Architecture | open | 185 | PASS | - |
| `TPM2-P2` Trusted Platform Module 2.0 Library Part 2: Structures | open | 185 | PASS | - |
| `TPM2-P3` Trusted Platform Module 2.0 Library Part 3: Commands | open | 185 | PASS | - |
| `TCG-PFP` TCG PC Client Platform Firmware Profile Specification | open | 1.06 Revision 52 | PASS | - |
| `DICE-HW` Hardware Requirements for a Device Identifier Composition Engine | open | 1.0 Revision 0.91 | PASS | The PDF has no bookmarks: the outline is parsed from the contents page, so section pages may be approximate (~). |
| `DICE-ATT` DICE Attestation Architecture | open | 1.2 | PASS | - |

## NIST Special Publications (platform firmware resiliency)

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `SP800-193` NIST SP 800-193 Platform Firmware Resiliency Guidelines | open | 2018 | PASS | The rotated 'available free of charge' margin text extracts as stray characters at the start of lines. |

## Arm server standards (SBMR, SBSA, BBR)

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `SBMR` Arm Server Base Manageability Requirements (DEN0069) | open | 3.0 | PASS | - |
| `SBSA` Arm Server Base System Architecture (DEN0029) | open | 8.0 | PASS | - |
| `BBR` Arm Base Boot Requirements (DEN0044) | open | 2.2 | PASS | - |

## UEFI, ACPI and PI

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `UEFI` Unified Extensible Firmware Interface (UEFI) Specification | open | 2.11 | PASS | - |
| `ACPI` Advanced Configuration and Power Interface (ACPI) Specification | open | 6.6 | PASS | - |
| `PI` UEFI Platform Initialization (PI) Specification | open | 1.10 | PASS | - |

## JEDEC memory and flash standards

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `JESD400-5` JESD400-5 DDR5 Serial Presence Detect (SPD) Contents | gated | - | - | - |
| `JESD216` JESD216 Serial Flash Discoverable Parameters (SFDP) | gated | - | - | - |
| `JESD251` JESD251 Expanded Serial Peripheral Interface (xSPI) for Non Volatile Memory Devices | gated | - | - | - |
| `JESD302` JESD302 DIMM Temperature Sensor (TS) and Serial Presence Detect (SPD) Hub | gated | - | - | - |

## MIPI I3C

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `MIPI-I3C-BASIC` MIPI I3C Basic Specification | gated | - | - | - |

## PCI Express

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `PCIE-BASE` PCI Express Base Specification | member | - | - | - |

## IEEE test access port (JTAG)

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `IEEE-1149.1` IEEE 1149.1 Standard Test Access Port and Boundary-Scan Architecture (JTAG) | member | - | - | - |

## SCSI Enclosure Services

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `SES` SCSI Enclosure Services (SES) | member | - | - | - |

## PICMG Hardware Platform Management

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `HPM.1` PICMG HPM.1 IPM Controller Firmware Upgrade Specification | member | - | - | - |
| `HPM.2` PICMG HPM.2 LAN-attached IPM Controller Specification | member | - | - | - |

## Compute Express Link

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `CXL` Compute Express Link (CXL) Specification | member | - | - | - |

## Intel platform interfaces under NDA (PECI, PFR, ASD, SPI)

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `PECI` Intel Platform Environment Control Interface (PECI) Specification | confidential | - | - | - |
| `PFR` Intel Platform Firmware Resilience (PFR) Specification | confidential | - | - | - |
| `ASD` Intel At-Scale Debug (ASD) Specification | confidential | - | - | - |
| `SPI-PG` Intel SPI Programming Guide | confidential | - | - | - |

## AMD platform management interfaces

| Document | Access | Latest | Verified | Known limit |
|---|---|---|---|---|
| `APML` AMD Advanced Platform Management Link (APML) and SB-RMI Specifications | confidential | - | - | - |
