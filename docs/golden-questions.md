# Golden Questions

The acceptance set for `bmc-spec`. Each question was answered by running
the skill's commands by hand against the documents and repositories the
tool fetched, and the answer was checked against the document. A release
is checked against this list; a contributor changing extraction, search,
tables, schema reading or Code Trees can re-run the affected rows.

The Document column names the catalog id and version each answer was
checked against (`-` for code-only questions); `catalog --table --golden
docs/golden-questions.md` reads it to mark those documents Verified.
Page numbers are physical PDF pages as `page` prints them. Where a
document's text layer is defective the row says so; that is a property of
the document, not of the tool.

## Documents

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G1 | Get Device ID: NetFn, command code, response fields | IPMI 2.0 rev 1.1; IPMI-UPDATE 2.0 rev 1.1 Errata 7 | IPMI 2.0 rev 1.1, section 20.1, PDF page 270; Appendix G, page 613 | `find IPMI "Get Device ID"`, `page IPMI 270`, `table IPMI --page 613` |
| G2 | Sensor type codes for Temperature, Voltage, Fan | IPMI 2.0 rev 1.1; IPMI-UPDATE 2.0 rev 1.1 Errata 7 | IPMI 2.0 rev 1.1, section 42.2, Sensor Type Codes table, page 531 | `table IPMI --page 531` (one Logical Table over pages 531-544) |
| G3 | Completion codes C1h, C7h, CCh | IPMI 2.0 rev 1.1; IPMI-UPDATE 2.0 rev 1.1 Errata 7 | IPMI 2.0 rev 1.1, section 5.2, page 70 | `page IPMI 70` |
| G4 | The BMC's default IPMB slave address | IPMI 2.0 rev 1.1; IPMI-UPDATE 2.0 rev 1.1 Errata 7 | IPMI 2.0 rev 1.1, sections 7.3 and 7.4, pages 97-99 (the IPMB document does not state it) | `find IPMI "20h"` |
| G5 | Get SEL Entry: command and NetFn | IPMI 2.0 rev 1.1; IPMI-UPDATE 2.0 rev 1.1 Errata 7 | IPMI 2.0 rev 1.1, section 31.5, page 450; Appendix G, page 615 | `section IPMI 31.5` |
| G6 | DCMI Group Extension id and Get DCMI Capabilities Info code | DCMI 1.5 | DCMI 1.5, section 6.1.1, Table 6-2, page 26 | `find DCMI "Group Extension"` |
| G7 | DCMI Get Power Reading / Get Power Limit / Set Power Limit codes | DCMI 1.5 | DCMI 1.5, section 6 command table, page 25; Tables 6-16 to 6-18, pages 42-44 | `table DCMI --page 25` |
| G8 | MCTP packet header byte by byte | DSP0236 1.3.3 | DSP0236 1.3.3, section 8.2, Table 1 and Figure 4, pages 24-25 | `page DSP0236 24 --to 25`, `render DSP0236 --page 25` (Figure 4 is a box-only diagram) |
| G9 | MCTP message type values for PLDM, NVMe-MI, SPDM | DSP0239 1.12.0 | DSP0239 1.12.0, section 7, Table 1, pages 13-14 (page 13 extracts without layout: an emoji in a NOTE) | `table DSP0239 --page 13` |
| G10 | SMBus command code carrying MCTP | DSP0237 1.2.0 | DSP0237 1.2.0, section 6.3, page 12 | `find DSP0237 "command code"` |
| G11 | PLDM message header layout | DSP0240 1.1.1 | DSP0240 1.1.1, section 7.1, page 23 | `page DSP0240 23` |
| G12 | PLDM type numbers | DSP0245 1.4.0 | DSP0245 1.4.0, section 8, Table 1 (written in binary) | `table DSP0245 --page N` from the `find` hit |
| G13 | GetPDR request fields and command code | DSP0248 1.3.1 | DSP0248 1.3.1, section 26.2.1, Table 69, page 122; Table 110, page 200 | `table DSP0248 --page 122` (joins pages 122-123) |
| G14 | RequestUpdate request fields | DSP0267 1.3.0 | DSP0267 1.3.0 (two fields more than 1.1.0), section 10 command tables | `find DSP0267 RequestUpdate`, `table` on the hit page |
| G15 | GetSensorReading response, spec and code | DSP0248 1.3.1 | DSP0248 1.3.1 Table 33; libpldm `decode_get_sensor_reading_resp`; pldm `platform-mc` | the two-part workflow |
| G16 | SPDM request and response codes for GET_VERSION, GET_CAPABILITIES, NEGOTIATE_ALGORITHMS | DSP0274 1.4.1 | DSP0274 1.4.1, Tables 4 and 5, pages 39-42 | `page DSP0274 39 --to 42` (these tables have no ruling lines) |
| G17 | Values of Chassis.PowerState | DSP8010 2026.1 | DSP8010 2026.1, `Chassis.v1_28_0.json` referring to `Resource.json#/definitions/PowerState`: seven values | `schema DSP8010 Chassis --property PowerState` |
| G18 | Creating a Redfish session and authenticating later requests | DSP0266 1.23.2 | DSP0266 1.23.2, sections 13.3.4.1 and 13.3.4.2 | `section DSP0266 13.3.4` |
| G19 | NVMe-MI opcodes of Read NVMe-MI Data Structure, NVM Subsystem Health Status Poll, Controller Health Status Poll | NVME-MI 2.1 | NVMe-MI 2.1, section 5, Figure 68, page 92 | `find NVME-MI "Opcode"` |
| G20 | What LTPI is in DC-SCM 2.x | DC-SCM Rev 2.1 Ver 1.1 | DC-SCM Rev 2.1 Ver 1.1, LTPI section; the signal details are in the separate LTPI specification, which the catalog does not hold | `find DC-SCM LTPI`, `render` (DC-SCM tables are images) |
| G21 | I2C speed modes and maximum bit rates | UM10204 Rev. 7.0 | UM10204 Rev. 7.0, section 5, page 33 | `section UM10204 "Bus speeds"` |

## MCTP transport bindings and message types

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G25 | PCIe Vendor ID and VDM message code that identify MCTP over PCIe VDM | DSP0238 1.4.0 | DSP0238 1.4.0, section 6.2.1 packet field table, page 12: Vendor ID 0x1AB4 (6836, DMTF), Message Code 0111_1111b (Type 1 VDM), MCTP VDM Code 0000b | `find DSP0238 1AB4`, `page DSP0238 12` |
| G26 | How an I3C Controller sends an MCTP packet to an I3C Target, and what follows the message data | DSP0233 1.0.1 | DSP0233 1.0.1, section 5.2.1, Figure 4 and Table 1, pages 15-16: a private write to the Target's dynamically assigned address carries the MCTP header and data, followed by a PEC byte (clause 5.3.1) | `section DSP0233 5.2`, `page DSP0233 16`, `render DSP0233 --page 16` |
| G27 | How an MCTP packet is framed on a serial link | DSP0253 1.0.0 | DSP0253 1.0.0, section 7, page 10: 0x7E flag first and last; 0x7E in the data becomes 0x7D 0x5E and 0x7D becomes 0x7D 0x5D; CRC-16 CCITT frame check; packet size is byte count + 4 | `find DSP0253 0x7E`, `page DSP0253 10` |
| G28 | Transport-specific MCTP control commands of the KCS binding | DSP0254 1.0.0 | DSP0254 1.0.0, section 7, Table 6, page 14: Register Endpoint 0xF0, Get MCTP Packet 0xF1, Enable MCTP SMS_ATN 0xF2 | `find DSP0254 "Register Endpoint"`, `table DSP0254 --page 14` |
| G29 | How a host finds an MCTP Host Interface in the SMBIOS tables | DSP0256 2.0.0 | DSP0256 2.0.0, section 9.1, Table 2, page 18: a Type 42 structure whose Interface Type is in the MCTP Host Interfaces range of DSP0239, with a Protocol Record of type MCTP (03h) carrying MCTP protocol version (WORD, 0x0103 for 1.3.1), link-layer type, instance number and characteristics | `find DSP0256 "Type 42"`, `page DSP0256 18` |
| G30 | USB interface descriptor values that identify an MCTP over USB interface | DSP0283 1.1.0 | DSP0283 1.1.0, section 6.2.1.1, Table 1, page 13: class 0x14, sub-class 0x0 (MC and managed device, no packet spanning; 0x1 host interface), protocol 0x1 (MCTP 1.x), two bulk endpoints; sub-class 0x2 with packet spanning in 6.2.2.1, page 15 | `find DSP0283 "Class code"`, `page DSP0283 13` |
| G31 | How an MCTP packet sits in an MMBI packet | DSP0284 1.0.1 | DSP0284 1.0.1, section 5.2, Table 1, page 10: MMBI packet type 0100b, header version 0001b, Null destination and source EIDs, padding to a 4-byte multiple | `find DSP0284 "Packet Type"`, `page DSP0284 10` (Figure 1's rotated labels extract as single letters; the bookmarks are anchors, so `section` finds nothing) |
| G32 | Layout of an MCTP message in an Extended PCC subspace | DSP0292 1.0.0 | DSP0292 1.0.0, sections 8.4 and 8.4.1, Figure 2, page 14: 16-byte header (PCC Signature, Flags, Length, Command = "MCTP", little-endian 0x5054434D), MCTP transport header at offset 16, message body from offset 20 | `find DSP0292 Signature`, `page DSP0292 14` |
| G33 | Which transport bindings NVMe Management Messages over MCTP are defined for, and where the message type number lives | DSP0235 1.0.1 | DSP0235 1.0.1, sections 7.1 and 7.2, page 9: DSP0237 (SMBus) and DSP0238 (PCIe); the number itself is assigned in DSP0239 (0x04, see G9) | `find DSP0235 "transport bindings"`, `page DSP0235 9` |
| G34 | MCTP message type of CXL FM API messages and their IC and TO bits | DSP0234 1.0.0 | DSP0234 1.0.0, section 7.4.1, Table 1, page 11: 0x07; IC 0b; TO 1b on requests and event notifications, 0b on responses | `find DSP0234 0x07`, `page DSP0234 11` |
| G35 | MCTP message type of CXL Type 3 CCI messages and the version reported | DSP0281 1.0.0 | DSP0281 1.0.0, sections 7.1 and 7.2, page 11: 0x08; version 1.0 reported as 0xF1F0FF00 | `find DSP0281 0x08`, `page DSP0281 11` |
| G36 | MCTP message type of PCIe-MI messages | DSP0291 1.0.0 | DSP0291 1.0.0, sections 9.1 and 9.2, page 13: 0x09; version 1.0 reported as 0xF1F0FF00 | `find DSP0291 "message type number"`, `page DSP0291 13` |

## PLDM companion specifications

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G37 | MCTP message type and IC bit of a PLDM message | DSP0241 1.0.0 | DSP0241 1.0.0, section 6.1, Table 1, page 8: PLDM = 0x01 (000_0001b), IC 0b | `find DSP0241 "Message Type"`, `page DSP0241 8` |
| G38 | PLDM File Transfer command codes and what DfOpen returns | DSP0242 1.0.1 | DSP0242 1.0.1, section 9, Table 6, page 27: DfOpen 0x01, DfClose 0x02, DfHeartbeat 0x03, DfProperties 0x10, DfGetFileAttribute 0x11, DfSetFileAttribute 0x12, DfRead 0x20 (MultipartReceive), DfFIFOSend 0x21 (MultipartSend); DfOpen returns the FileDescriptor used by DfRead, DfHeartbeat and DfClose (9.2, page 29) | `find DSP0242 "Command Codes"`, `page DSP0242 27` (Table 6 has no ruling lines) |
| G39 | PLDM for SMBIOS Data Transfer command codes | DSP0246 1.0.1 | DSP0246 1.0.1, section 8.2, Table 3, page 11: GetSMBIOSStructureTableMetadata 0x01, SetSMBIOSStructureTableMetadata 0x02, GetSMBIOSStructureTable 0x03, SetSMBIOSStructureTable 0x04, GetSMBIOSStructureByType 0x05, GetSMBIOSStructureByHandle 0x06 | `find DSP0246 GetSMBIOSStructureTable`, `table DSP0246 --page 11` |
| G40 | PLDM for BIOS Control and Configuration command codes | DSP0247 1.0.0 | DSP0247 1.0.0, section 8, Table 31, page 35: GetBIOSTable 0x01, SetBIOSTable 0x02, UpdateBIOSTable 0x03, GetBIOSTableTags 0x04, SetBIOSTableTags 0x05, AcceptBIOSAttributesPendingValues 0x06, SetBIOSAttributeCurrentValue 0x07, GetBIOSAttributeCurrentValueByHandle 0x08, GetBIOSAttributePendingValueByHandle 0x09, GetBIOSAttributeCurrentValueByType 0x0a, GetBIOSAttributePendingValueByType 0x0b, GetDateTime 0x0c | `find DSP0247 GetBIOSTable`, `page DSP0247 35` |
| G41 | State set ID and values of Health State | DSP0249 1.4.0 | DSP0249 1.4.0, section 6.3, Table 1, page 12: set 1; 1 Normal/OK, 2 Non-Critical/Warning, 3 Critical, 4 Fatal, 5 Upper Non-Critical, 6 Lower Non-Critical, 7 Upper Critical, 8 Lower Critical, 9 Upper Fatal, 10 Lower Fatal | `find DSP0249 "Health State"`, `page DSP0249 12` |
| G42 | PLDM for FRU Data command codes | DSP0257 2.0.0 | DSP0257 2.0.0, section 13, Table 7, page 23: GetFRURecordTableMetadata 0x01, GetFRURecordTable 0x02, SetFRURecordTable 0x03, GetFRURecordByOption 0x04, ReadFRUDataItem 0x10, WriteFRUDataItem 0x11, FindFRUFiles 0x18, GetFRUFileMetadata 0x19 | `find DSP0257 "Command Codes"`, `page DSP0257 23` |
| G43 | RDE command codes | DSP0218 1.2.0 | DSP0218 1.2.0, section 10, Table 51, pages 111-113: NegotiateRedfishParameters 0x01, NegotiateMediumParameters 0x02, GetSchemaDictionary 0x03, GetSchemaURI 0x04, GetResourceETag 0x05, GetOEMCount 0x06 to GetSchemaFile 0x0C, RDEOperationInit 0x10, SupplyCustomRequestParameters 0x11, RetrieveCustomResponseParameters 0x12, RDEOperationComplete 0x13, RDEOperationStatus 0x14, RDEOperationKill 0x15, RDEOperationEnumerate 0x16, RDEMultipartSend 0x30, RDEMultipartReceive 0x31 | `find DSP0218 NegotiateMediumParameters`, `table DSP0218 --page 111` (one Logical Table over pages 111-113) |

## SPDM companion specifications

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G44 | MCTP message type of SPDM and the version it reports | DSP0275 1.0.2 | DSP0275 1.0.2, sections 4.5.1 and 4.7, page 9: SPDM = 0x05 (000_0101b), IC 0b; version 1.0.2 reported as 0xF1F0F200 | `find DSP0275 "message type"`, `page DSP0275 9` |
| G45 | MCTP message type of Secured Messages and the size of the Partial Sequence Number | DSP0276 1.3.0 | DSP0276 1.3.0, section 4, Figure 1, page 8: message type 6, IC 0; Partial Sequence Number is 2 bytes, the low 16 bits of the DSP0277 sequence number | `find DSP0276 "message type 6"`, `page DSP0276 8` |
| G46 | Fields of a Secured Message | DSP0277 1.3.0 | DSP0277 1.3.0, section 5.1, Figure 1 and Table 1, pages 10-13: Session ID (4 bytes), Sequence Number (S bytes, set by the transport binding), Length (4), Application Data Length (4), Application Data, Random Data, MAC | `find DSP0277 "Session ID"`, `page DSP0277 11 --to 13` |
| G47 | SCSI SECURITY PROTOCOL value for SPDM and how the SPDM operation is passed | DSP0286 1.0.0 | DSP0286 1.0.0, sections 7.2.2.1 and 7.2.2.2, Tables 17 and 18, pages 33-34: SECURITY PROTOCOL 0xE8; SECURITY PROTOCOL SPECIFIC bits [1:0] ConnectionID, bits [7:2] SPDMOperation | `find DSP0286 0xE8`, `page DSP0286 33 --to 34` |
| G48 | TCP port assigned to SPDM | DSP0287 1.0.0 | DSP0287 1.0.0, section 5, page 9: IANA port 4194; one SPDM communication does not span TCP connections | `find DSP0287 4194` |
| G49 | Generic Authorization message header and how request and response codes are told apart | DSP0289 1.0.0 | DSP0289 1.0.0, section 9.1.6, Table 15, page 50: byte 0 RequestResponseCode (0x00 to 0x7F responses, 0x80 to 0xFF requests), byte 1 reserved, payload from byte 2; an unsupported request gets AUTH_ERROR with ErrorCode UnsupportedRequest | `section DSP0289 9.1.6`, `page DSP0289 50` |

## NC-SI

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G50 | EtherType of NC-SI Control Packets and the Get Link Status command and response codes | DSP0222 1.2.1 | DSP0222 1.2.1, section 8.1.1, Table 9, page 69: EtherType 0x88F8, destination address broadcast; sections 8.4.23 and 8.4.24, page 98: command 0x0A, response 0x8A | `find DSP0222 0x88F8`, `section DSP0222 8.4.23`, `page DSP0222 98` |
| G51 | MCTP message types used by NC-SI over MCTP | DSP0261 1.3.1 | DSP0261 1.3.1, section 5.3, Table 1, page 12: NC-SI Control 0x02, Ethernet (Pass-through) 0x03 | `find DSP0261 "Message types"`, `table DSP0261 --page 12` |
| G52 | How NC-SI is exposed over USB | DSP0296 1.0.0 | DSP0296 1.0.0, sections 8.1 and 8.2, page 11: the NCs are USB functions on a bus whose host controller is the MC, exposed as a CDC ECM or NCM subclass; up to eight packages with 31 channels each; an NC may share a composite device with an MCTP over USB (DSP0283) function | `section DSP0296 8.2`, `page DSP0296 11` |

## SMBIOS

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G53 | Which structures a compliant SMBIOS implementation must provide | DSP0134 3.9.0 | DSP0134 3.9.0, section 6.2, Table 4, pages 28-29: Firmware Information (Type 0), System Information (1), System Enclosure (3), Processor Information (4), Cache Information (7), System Slots (9), Physical Memory Array (16), Memory Device (17), Memory Array Mapped Address (19), System Boot Information (32) | `section DSP0134 6.2`, `table DSP0134 --page 28` (one Logical Table over pages 28-29) |

## OpenBMC

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G22 | Where bmcweb reads Chassis PowerState from | - | bmcweb master (2026-09-03), `redfish-core/lib/chassis.hpp`, D-Bus `CurrentPowerState` of `xyz.openbmc_project.State.Chassis`, four states mapped | `clone bmcweb`, `grep bmcweb CurrentPowerState`, `code bmcweb redfish-core/lib/chassis.hpp --lines 160-220` |
| G23 | How Get Device ID is registered in phosphor-host-ipmid | - | `apphandler.cpp`, `registerHandler(..., netFnApp, cmdGetDeviceId, ...)`; `cmdGetDeviceId = 0x01` in `include/ipmid/api-types.hpp` | `grep phosphor-host-ipmid cmdGetDeviceId` |
| G24 | Which pldm code sends RequestUpdate and which libpldm function encodes it | - | pldm `fw-update/device_updater.cpp` calls `encode_request_update_req`; libpldm `src/dsp/firmware_update.c`; at the OpenBMC 2.18.0 pin the pldm call sits on another line | `clone pldm --release 2.18.0`, `grep pldm encode_request_update_req --release 2.18.0` |

## Named table checks

| Table | Command | Expected |
|---|---|---|
| IPMI 2.0 Table 5-1 Network Function Codes | `table IPMI --page 68` | one Logical Table, pages 67-68, header once |
| IPMI 2.0 Table G-1 Command Number Assignments and Privilege Levels | `table IPMI --page 615` | one Logical Table, pages 613-617, 213 rows |
| IPMI 2.0 Table 42-3 Sensor Type Codes | `table IPMI --page 540` | one Logical Table, pages 531-544, 48 rows; the row cut at 535/536 joined |
| DSP0248 Table 69 GetPDR command format | `table DSP0248 --page 122` | pages 122-123, the `(continued)` header row dropped |

## Spec versus code

Chassis PowerState as a two-part answer: the schema allows seven values,
bmcweb maps four D-Bus states onto On, Off, PoweringOff and PoweringOn;
Paused, Sleeping and Hibernating are never produced. The difference is a
finding, not an error.

## Freshness

`check` against the publishers on 2026-09-04: every DMTF document
current; NVMe lists Management Interface 2.2 and NVMe over PCIe Transport
1.4 (added to the catalog with `refresh --write`); the OCP wiki lists
M-CRPS 1.06 as a Google Drive link, which the catalog records in the
document's notes until a download URL exists. DC-SCM Rev 2.2 Ver 1.0 has
been in the catalog as a direct opencompute.org PDF since M8a; only Rev
2.0 Ver 1.0 remains a Google Drive link, listed so that `fetch` prints the
browser instruction and `check DC-SCM` reports current.
