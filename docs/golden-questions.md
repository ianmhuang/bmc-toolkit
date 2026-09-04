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
M-CRPS 1.06 and DC-SCM 2.2 as Google Drive links, which the catalog
records in the documents' notes until a download URL exists.
