# Support Level

What the tool can tell you about every document in the Source Catalog:
one table per family, generated from `bmc_toolkit/spec/catalog.toml` and
`docs/golden-questions.md`, never edited by hand.

- **Document**: the catalog id (what you pass to `fetch`, `find`, `page`
  and the other commands) and the document's title.
- **Access**: `open` (the tool downloads it), `gated` (free registration or
  a request to the publisher), `member`, `confidential` (NDA). `open
  (latest gated)` means the newest version sits behind a registration and
  `fetch` takes the newest open one.
- **Latest**: the newest published version the catalog lists; `-` when a
  manual document lists none.
- **Fetch**: `direct` from the publisher, `wayback` from the Internet
  Archive's copy (publishers that refuse scripted downloads), `manual
  (Drop-in)`: never downloaded, registered with `add` when you have a copy.
- **Verified**: the Golden Questions answered against the document, with
  the version they were checked on. Every open document has at least one.
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

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `IPMI` Intelligent Platform Management Interface Specification, Second Generation, v2.0 | open | 2.0 rev 1.1 | direct | G1, G2, G3, G4, G5 (2.0 rev 1.1) | Table numbers are missing from the PDF's text layer; tables are cited by title. |
| `IPMI-UPDATE` IPMI Specification, Second Generation, v2.0 Specification Update (Errata/Addenda/Clarifications) | open | 2.0 rev 1.1 Errata 7 | direct | G1, G2, G3, G4, G5 (2.0 rev 1.1 Errata 7) | - |
| `IPMB` Intelligent Platform Management Bus Communications Protocol Specification | open | 1.0 | direct | G25 (1.0) | PDF bookmarks carry titles without section numbers: section by title, not by number. |
| `IPMI-FRU` Platform Management FRU Information Storage Definition | open | 1.0 rev 1.3 | direct | G26 (1.0 rev 1.3) | - |
| `DCMI` Data Center Manageability Interface Specification | open | 1.5 | direct | G6, G7 (1.5) | - |

## Enhanced Serial Peripheral Interface

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `ESPI` Enhanced Serial Peripheral Interface (eSPI) Base Specification | open | 1.6 | direct | G27 (1.6) | - |

## Management Component Transport Protocol

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `DSP0236` Management Component Transport Protocol (MCTP) Base Specification | open | 1.3.3 | direct | G8 (1.3.3) | - |
| `DSP0237` Management Component Transport Protocol (MCTP) SMBus/I2C Transport Binding Specification | open | 1.2.0 | direct | G10 (1.2.0) | PDF bookmarks are cross-reference anchors, not headings: section finds nothing and cites name an anchor; use find and page. |
| `DSP0238` Management Component Transport Protocol (MCTP) PCIe® VDM Transport Binding Specification | open | 1.4.0 | direct | G46 (1.4.0) | - |
| `DSP0239` Management Component Transport Protocol (MCTP) IDs and Codes Specification | open | 1.12.0 | direct | G9 (1.12.0) | One page holds an emoji that breaks pdfium's character order; extracted without layout. |
| `DSP0233` Management Component Transport Protocol (MCTP) I3C Transport Binding Specification | open | 1.0.1 | direct | G47 (1.0.1) | - |
| `DSP0253` MCTP Serial Transport Binding Specification | open | 1.0.0 | direct | G48 (1.0.0) | Some PDF bookmarks are cross-reference anchors; a cite may name one instead of the heading. |
| `DSP0254` MCTP KCS Transport Binding Specification | open | 1.0.0 | direct | G49 (1.0.0) | Some PDF bookmarks are cross-reference anchors; a cite may name one instead of the heading. |
| `DSP0256` Management Component Transport Protocol (MCTP) Host Interface Specification | open | 2.0.0 | direct | G50 (2.0.0) | - |
| `DSP0283` Management Component Transport Protocol (MCTP) Universal Serial Bus (USB) Transport Binding Specification | open | 1.1.0 | direct | G51 (1.1.0) | - |
| `DSP0284` Management Component Transport Protocol (MCTP) Memory-Mapped Buffer Interface (MMBI) Transport Binding Specification | open | 1.0.1 | direct | G52 (1.0.1) | PDF bookmarks are cross-reference anchors as well as headings: section 5.2 is found, but a page cite can name the anchor before the heading (page 10 cites 5.1.3 for section 5.2); check the heading in the page text. Figure 1's rotated labels extract as single letters; use render. |
| `DSP0292` Management Component Transport Protocol (MCTP) PCC Transport Binding Specification | open | 1.0.0 | direct | G53 (1.0.0) | - |
| `DSP0235` NVMe™ (NVMe Express™) Management Messages over MCTP Binding Specification | open | 1.0.1 | direct | G54 (1.0.1) | PDF bookmarks are cross-reference anchors, not headings: section finds nothing and cites name an anchor; use find and page. |
| `DSP0234` CXL™ Fabric Manager API over MCTP Binding Specification | open | 1.0.0 | direct | G55 (1.0.0) | PDF bookmarks are cross-reference anchors, not headings: section finds nothing and cites name an anchor; use find and page. |
| `DSP0281` CXL™ Type 3 Device Component Command Interface over MCTP Binding Specification | open | 1.0.0 | direct | G56 (1.0.0) | - |
| `DSP0291` PCIe® Management Interface (PCIe-MI®) over MCTP Binding Specification | open | 1.0.0 | direct | G57 (1.0.0) | - |

## Platform Level Data Model

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `DSP0240` Platform Level Data Model (PLDM) Base Specification | open | 1.1.1 | direct | G11 (1.1.1) | - |
| `DSP0241` Platform Level Data Model (PLDM) Over MCTP Binding Specification | open | 1.0.0 | direct | G58 (1.0.0) | - |
| `DSP0242` Platform Level Data Model (PLDM) for File Transfer Specification | open | 1.0.1 | direct | G59 (1.0.1) | - |
| `DSP0245` Platform Level Data Model (PLDM) IDs and Codes Specification | open | 1.4.0 | direct | G12 (1.4.0) | - |
| `DSP0246` Platform Level Data Model (PLDM) for SMBIOS Transfer Specification | open | 1.0.1 | direct | G60 (1.0.1) | - |
| `DSP0247` Platform Level Data Model (PLDM) for BIOS Control and Configuration Specification | open | 1.0.0 | direct | G61 (1.0.0) | - |
| `DSP0248` PLDM Platform Monitoring and Control Specification | open | 1.3.1 | direct | G13, G15 (1.3.1) | - |
| `DSP0249` Platform Level Data Model (PLDM) State Set Specification | open | 1.4.0 | direct | G62 (1.4.0) | - |
| `DSP0257` Platform Level Data Model (PLDM) for FRU Data Specification | open | 2.0.0 | direct | G63 (2.0.0) | - |
| `DSP0267` Platform Level Data Model (PLDM) for Firmware Update Specification | open | 1.3.0 | direct | G14 (1.3.0) | - |
| `DSP0218` Platform Level Data Model (PLDM) for Redfish Device Enablement | open | 1.2.0 | direct | G64 (1.2.0) | - |

## Security Protocol and Data Model

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `DSP0274` Security Protocol and Data Model (SPDM) Specification | open | 1.4.1 | direct | G16 (1.4.1) | Most tables have no ruling lines; they are drawn as cell boxes, which table reads (the table: line says cells). |
| `DSP0275` Security Protocol and Data Model (SPDM) over MCTP Binding Specification | open | 1.0.2 | direct | G65 (1.0.2) | - |
| `DSP0276` Secured Messages using SPDM over MCTP Binding Specification | open | 2.0.0 | direct | G66 (2.0.0) | - |
| `DSP0277` Secured Messages Using SPDM Specification | open | 2.0.0 | direct | G67 (2.0.0) | - |
| `DSP0286` Security Protocol and Data Model (SPDM) to Storage Binding Specification | open | 1.0.0 | direct | G68 (1.0.0) | - |
| `DSP0287` SPDM over TCP Binding Specification | open | 1.0.0 | direct | G69 (1.0.0) | - |
| `DSP0289` Security Protocol and Data Model (SPDM) Authorization Specification | open | 1.0.0 | direct | G70 (1.0.0) | - |

## Network Controller Sideband Interface

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `DSP0222` Network Controller Sideband Interface (NC-SI) Specification | open | 1.2.1 | direct | G71 (1.2.1) | - |
| `DSP0261` NC-SI over MCTP Binding Specification | open | 1.3.1 | direct | G72 (1.3.1) | - |
| `DSP0296` Network Controller Sideband Interface (NC‐SI) over Ethernet over USB Binding Specification | open | 1.0.0 | direct | G73 (1.0.0) | - |

## System Management BIOS

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `DSP0134` SMBIOS Specification | open | 3.9.0 | direct | G74 (3.9.0) | - |

## Redfish

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `DSP0266` Redfish Specification | open | 1.24.0 | direct | G18 (1.23.2) | - |
| `DSP8010` Redfish Schema Bundle | open | 2026.1 | direct | G17 (2026.1) | - |
| `DSP0268` Redfish Data Model Specification | open | 2026.1 | direct | G75 (2026.1) | - |
| `DSP2046` Redfish Resource and Schema Guide | open | 2026.1 | direct | G76 (2026.1) | - |
| `DSP0270` Redfish Host Interface Specification | open | 1.3.1 | direct | G77 (1.3.1) | - |
| `DSP0272` Redfish Interoperability Profiles Specification | open | 1.10.0 | direct | G78 (1.10.0) | - |
| `DSP2053` Redfish Property Guide | open | 2026.1 | direct | G79 (2026.1) | The whole guide is one property table over 300-odd pages: table prints the rows that start on the asked page and says so (--all-rows prints every row). |
| `DSP2065` Redfish Message Registry Guide | open | 2026.1 | direct | G80 (2026.1) | - |
| `DSP8011` Redfish Standard Registries Bundle | open | 2026.1 | direct | G101 (2026.1) | ZIP of registries: registry reads the message registries (newest file per registry); the privilege registries, the HTML and the PDF stay in the archive (DSP2065 is the PDF's own catalog entry). |
| `DSP8013` Redfish Interoperability Profiles Bundle | open | 2026.1 | direct | G102 (2026.1) | ZIP of profiles: schema reads the profile schema (RedfishInteroperabilityProfile); the bundle holds no profile documents, and its PDF stays in the archive (DSP0272 is the PDF's own catalog entry). |

## NVM Express

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `NVME-BASE` NVM Express Base Specification | open | 2.4 | direct | G30 (2.4) | - |
| `NVME-MI` NVM Express Management Interface Specification | open | 2.2 | direct | G19 (2.1); G31 (2.2) | - |
| `NVME-PCIE` NVM Express over PCIe Transport Specification | open | 1.4 | direct | G32 (1.4) | - |

## OCP Datacenter-ready Secure Control Module

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `DC-SCM` Datacenter-ready Secure Control Module (DC-SCM) Specification | open | Rev 2.2 Ver 1.0 | direct | G20 (Rev 2.1 Ver 1.1) | Tables are images: use page and render; table finds nothing on those pages. |
| `LTPI` DC-SCM LVDS Tunneling Protocol and Interface (LTPI) Specification | open | Rev 1.2 Ver 1.0 | direct | G33 (Rev 1.2 Ver 1.0) | - |

## OCP Datacenter Modular Hardware System

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `M-CRPS` DC-MHS Modular Hardware System Common Redundant Power Supply (M-CRPS) Base Specification | open | R1 v1.0 RC4 | direct | G34 (R1 v1.0 RC4) | - |
| `M-PIC` DC-MHS Platform Infrastructure Connectivity (M-PIC) Specification | open | R1 v1.11 | direct | G35 (R1 v1.11) | - |
| `M-XIO` DC-MHS Extensible I/O (M-XIO) Specification | open | R1 v1.04 RC1 | direct | G36 (R1 v1.04 RC1) | - |
| `M-DNO` DC-MHS Densified Node Operation (M-DNO) Specification | open | R1 v1.1 RC2 | direct | G37 (R1 v1.1 RC2) | - |
| `M-FLW` DC-MHS Full Width HPM (M-FLW) Specification | open | R1 v1.2 RC3 | direct | G38 (R1 v1.2 RC3) | - |
| `M-PESTI` DC-MHS Peripheral Sideband Tunneling Interface (M-PESTI) Specification | open | R1 v1.2 RC2 | direct | G39 (R1 v1.2 RC2) | - |
| `M-SDNO` DC-MHS Shared-Infrastructure Densified Node Operation (M-SDNO) Specification | open | v1.1 RC2 | direct | G40 (v1.1 RC2) | - |

## I2C bus

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `UM10204` I2C-bus specification and user manual (UM10204) | open | Rev. 7.0 | direct | G21 (Rev. 7.0) | - |

## System Management Bus

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `SMBUS` System Management Bus (SMBus) Specification | open | 3.3.1 | direct | G41 (3.3.1) | - |

## Common Management Interface Specification (optical modules)

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `CMIS` Common Management Interface Specification (OIF-CMIS) | open | 5.4 | direct | G42 (5.4) | Tables have no ruling lines on a few pages; those are drawn as cell boxes, which table reads (the table: line says cells). |

## Low Pin Count interface

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `LPC` Low Pin Count (LPC) Interface Specification | open | 1.1 | direct | G28 (1.1) | - |

## PWM fan control

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `PWM-FAN` 4-Wire Pulse Width Modulation (PWM) Controlled Fans Specification | open | Rev 1.3 | wayback | G29 (Rev 1.3) | - |

## SFF specifications (SGPIO, module EEPROMs)

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `SFF-8485` SFF-8485 Specification for Serial GPIO (SGPIO) Bus | open | Rev 0.7 | direct | G43 (Rev 0.7) | - |
| `SFF-8472` SFF-8472 Specification for Management Interface for SFP+ | open | Rev 12.5a | direct | G84 (Rev 12.5a) | - |
| `SFF-8636` SFF-8636 Specification for Management Interface for 4-lane Modules and Cables | open | Rev 2.12 | direct | G85 (Rev 2.12) | - |
| `SFF-8024` SFF-8024 Specification for SFF Module Management Reference Code Tables | open | Rev 4.14 | direct | G86 (Rev 4.14) | - |

## Power Management Bus

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `PMBUS-I` PMBus Power System Management Protocol Specification Part I: General Requirements, Transport and Electrical Interface | open (latest gated) | 1.5 | direct | G44 (1.3.1) | - |
| `PMBUS-II` PMBus Power System Management Protocol Specification Part II: Command Language | open (latest gated) | 1.5 | direct | G45 (1.3.1) | - |

## OCP Security (root of trust, attestation)

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `CALIPTRA` Caliptra: A Datacenter System on a Chip (SoC) Root of Trust (RoT) Modular Base Specification | open | 2.0 | direct | G81 (2.0) | - |
| `OCP-ATTEST` Attestation of System Components v1.0: Requirements and Recommendations | open | 1.0 | direct | G82 (1.0) | The PDF has no bookmarks and no contents page: section finds nothing; use find and page. |

## OCP NIC 3.0

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `OCP-NIC` OCP NIC 3.0 Design Specification | open | 1.6.0 | direct | G83 (1.6.0) | The document is line-numbered; page text carries the numbers, so a find hit may start with the line number. |

## Trusted Computing Group (TPM 2.0, PC Client firmware profile, DICE)

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `TPM2-P0` Trusted Platform Module 2.0 Library Part 0: Introduction | open | 185 | wayback | G91 (185) | - |
| `TPM2-P1` Trusted Platform Module 2.0 Library Part 1: Architecture | open | 185 | wayback | G92 (185) | - |
| `TPM2-P2` Trusted Platform Module 2.0 Library Part 2: Structures | open | 185 | wayback | G93 (185) | - |
| `TPM2-P3` Trusted Platform Module 2.0 Library Part 3: Commands | open | 185 | wayback | G94 (185) | - |
| `TCG-PFP` TCG PC Client Platform Firmware Profile Specification | open | 1.06 Revision 52 | wayback | G95 (1.06 Revision 52) | - |
| `DICE-HW` Hardware Requirements for a Device Identifier Composition Engine | open | 1.0 Revision 0.91 | wayback | G96 (1.0 Revision 0.91) | The PDF has no bookmarks: the outline is parsed from the contents page, so section pages may be approximate (~). |
| `DICE-ATT` DICE Attestation Architecture | open | 1.2 | wayback | G97 (1.2) | - |

## NIST Special Publications (platform firmware resiliency)

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `SP800-193` NIST SP 800-193 Platform Firmware Resiliency Guidelines | open | 2018 | direct | G87 (2018) | The rotated 'available free of charge' margin text extracts as stray characters at the start of lines. |

## Arm server standards (SBMR, SBSA, BBR)

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `SBMR` Arm Server Base Manageability Requirements (DEN0069) | open | 3.0 | direct | G88 (3.0) | - |
| `SBSA` Arm Server Base System Architecture (DEN0029) | open | 8.0 | direct | G89 (8.0) | - |
| `BBR` Arm Base Boot Requirements (DEN0044) | open | 2.2 | direct | G90 (2.2) | - |

## UEFI, ACPI and PI

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `UEFI` Unified Extensible Firmware Interface (UEFI) Specification | open | 2.11 | wayback | G98 (2.11) | - |
| `ACPI` Advanced Configuration and Power Interface (ACPI) Specification | open | 6.6 | wayback | G99 (6.6) | - |
| `PI` UEFI Platform Initialization (PI) Specification | open | 1.10 | wayback | G100 (1.10) | - |

## JEDEC memory and flash standards

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `JESD400-5` JESD400-5 DDR5 Serial Presence Detect (SPD) Contents | gated | - | manual (Drop-in) | - | - |
| `JESD216` JESD216 Serial Flash Discoverable Parameters (SFDP) | gated | - | manual (Drop-in) | - | - |
| `JESD251` JESD251 Expanded Serial Peripheral Interface (xSPI) for Non Volatile Memory Devices | gated | - | manual (Drop-in) | - | - |
| `JESD302` JESD302 DIMM Temperature Sensor (TS) and Serial Presence Detect (SPD) Hub | gated | - | manual (Drop-in) | - | - |

## MIPI I3C

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `MIPI-I3C-BASIC` MIPI I3C Basic Specification | gated | - | manual (Drop-in) | - | - |

## PCI Express

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `PCIE-BASE` PCI Express Base Specification | member | - | manual (Drop-in) | - | - |

## IEEE test access port (JTAG)

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `IEEE-1149.1` IEEE 1149.1 Standard Test Access Port and Boundary-Scan Architecture (JTAG) | member | - | manual (Drop-in) | - | - |

## SCSI Enclosure Services

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `SES` SCSI Enclosure Services (SES) | member | - | manual (Drop-in) | - | - |

## PICMG Hardware Platform Management

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `HPM.1` PICMG HPM.1 IPM Controller Firmware Upgrade Specification | member | - | manual (Drop-in) | - | - |
| `HPM.2` PICMG HPM.2 LAN-attached IPM Controller Specification | member | - | manual (Drop-in) | - | - |

## Compute Express Link

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `CXL` Compute Express Link (CXL) Specification | member | - | manual (Drop-in) | - | - |

## Intel platform interfaces under NDA (PECI, PFR, ASD, SPI)

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `PECI` Intel Platform Environment Control Interface (PECI) Specification | confidential | - | manual (Drop-in) | - | - |
| `PFR` Intel Platform Firmware Resilience (PFR) Specification | confidential | - | manual (Drop-in) | - | - |
| `ASD` Intel At-Scale Debug (ASD) Specification | confidential | - | manual (Drop-in) | - | - |
| `SPI-PG` Intel SPI Programming Guide | confidential | - | manual (Drop-in) | - | - |

## AMD platform management interfaces

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `APML` AMD Advanced Platform Management Link (APML) and SB-RMI Specifications | confidential | - | manual (Drop-in) | - | - |

## ASPEED BMC SoC datasheets

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `AST2500` ASPEED AST2500 Datasheet | confidential | - | manual (Drop-in) | - | - |
| `AST2600` ASPEED AST2600 Datasheet | confidential | - | manual (Drop-in) | - | - |

## Nuvoton BMC SoC datasheets

| Document | Access | Latest | Fetch | Verified | Known limit |
|---|---|---|---|---|---|
| `NPCM7XX` Nuvoton NPCM7xx (Poleg) Datasheet | confidential | - | manual (Drop-in) | - | - |
| `NPCM8XX` Nuvoton NPCM8xx (Arbel) Datasheet | confidential | - | manual (Drop-in) | - | - |
