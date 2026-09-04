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

Rows G25 onwards were added in M8, one per document that had none. Their
ids follow file order, which is catalog order by family. The answer
column records the identifying values (codes, offsets, names) from these
open documents on purpose, so that a re-run can be checked without the
PDF at hand; prose is paraphrased, not copied, while registry message
strings (DSP2065 and the like) are quoted verbatim, since the exact text
is what a client matches on. A document whose Latest is gated is verified
on its newest open version and the row says so.

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
| G9 | MCTP message type values for PLDM, NVMe-MI, SPDM | DSP0239 1.12.0 | DSP0239 1.12.0, section 7, Table 1, pages 13-14 (page 13 extracts without layout: an emoji in a NOTE) | `table DSP0239 --page 13` (one Logical Table over pages 13-14, drawn as cell boxes), `page DSP0239 13 --to 14` |
| G10 | SMBus command code carrying MCTP | DSP0237 1.2.0 | DSP0237 1.2.0, section 6.3, page 12 | `find DSP0237 "command code"` |
| G11 | PLDM message header layout | DSP0240 1.1.1 | DSP0240 1.1.1, section 7.1, page 23 | `page DSP0240 23` |
| G12 | PLDM type numbers | DSP0245 1.4.0 | DSP0245 1.4.0, section 8, Table 1 (written in binary) | `find DSP0245 "PLDM Types"`, `table DSP0245 --page 11` (cell boxes) |
| G13 | GetPDR request fields and command code | DSP0248 1.3.1 | DSP0248 1.3.1, section 26.2.1, Table 69, page 122; Table 110, page 200 | `table DSP0248 --page 122` (joins pages 122-123) |
| G14 | RequestUpdate request fields | DSP0267 1.3.0 | DSP0267 1.3.0 (two fields more than 1.1.0), section 10 command tables | `find DSP0267 RequestUpdate`, `table` on the hit page |
| G15 | GetSensorReading response, spec and code | DSP0248 1.3.1 | DSP0248 1.3.1 Table 33; libpldm `decode_get_sensor_reading_resp`; pldm `platform-mc` | the two-part workflow |
| G16 | SPDM request and response codes for GET_VERSION, GET_CAPABILITIES, NEGOTIATE_ALGORITHMS | DSP0274 1.4.1 | DSP0274 1.4.1, Tables 4 and 5, pages 39-42 | `table DSP0274 --page 39` (Table 4, pages 39-41) and `table DSP0274 --page 42` (Table 5, pages 41-43); both drawn as cell boxes |
| G17 | Values of Chassis.PowerState | DSP8010 2026.1 | DSP8010 2026.1, `Chassis.v1_28_0.json` referring to `Resource.json#/definitions/PowerState`: seven values | `schema DSP8010 Chassis --property PowerState` |
| G18 | Creating a Redfish session and authenticating later requests | DSP0266 1.23.2 | DSP0266 1.23.2, sections 13.3.4.1 and 13.3.4.2 | `section DSP0266 13.3.4` |
| G19 | NVMe-MI opcodes of Read NVMe-MI Data Structure, NVM Subsystem Health Status Poll, Controller Health Status Poll | NVME-MI 2.1 | NVMe-MI 2.1, section 5, Figure 68, page 92 | `find NVME-MI "Opcode"` |
| G20 | What LTPI is in DC-SCM 2.x | DC-SCM Rev 2.1 Ver 1.1 | DC-SCM Rev 2.1 Ver 1.1, LTPI section; the signal details are in the separate LTPI specification, which the catalog does not hold | `find DC-SCM LTPI`, `render` (DC-SCM tables are images) |
| G21 | I2C speed modes and maximum bit rates | UM10204 Rev. 7.0 | UM10204 Rev. 7.0, section 5, page 33 | `section UM10204 "Bus speeds"` |

## IPMB and FRU

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G25 | IPMB request and response message layout | IPMB 1.0 | IPMB 1.0, section 2.11.1, Figure 2-2, PDF page 25 (printed 19): request rsSA, netFn (even)/rsLUN, checksum, rqSA, rqSeq/rqLUN, cmd, data bytes, checksum; response rqSA, netFn (odd)/rqLUN, checksum, rsSA, rqSeq/rsLUN, cmd, completion code, response data, checksum; checksums are 2's complement (page 10) | `section IPMB "Message Transaction"` (the IPMB bookmarks carry no section numbers), `find IPMB rqSeq`, `render IPMB --page 25` (the format is a figure) |
| G26 | FRU Common Header layout | IPMI-FRU 1.0 rev 1.3 | IPMI-FRU 1.0 rev 1.3, section 8, Table 8-1, PDF page 11 (printed 5): format version (1h), then starting offsets in multiples of 8 bytes for the Internal Use, Chassis Info, Board, Product Info and MultiRecord areas (00h = absent), a pad byte and a zero checksum; eight bytes in all | `section IPMI-FRU 8`, `table IPMI-FRU --page 11` |

## eSPI, LPC and PWM fans

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G27 | eSPI channel numbers and what each carries | ESPI 1.6 | eSPI 1.6, section 2.2, Figure 9, page 18: channel 0 peripheral (host bridge to endpoint), channel 1 virtual wires (tunneled sideband pins), channel 2 out-of-band tunneled SMBus, channel 3 flash access; all share one chip select and the data and clock pins | `find ESPI "Channel 3"`, `page ESPI 18` |
| G28 | LPC START field encodings | LPC 1.1 | LPC 1.1, section 4.2.1.1, page 15: 0000 start of a target cycle (memory, I/O, DMA), 0010 and 0011 grant for bus master 0 and 1, 1101 firmware memory read, 1110 firmware memory write, 1111 stop/abort; CYCTYPE + DIR encodings follow in 4.2.1.2 | `section LPC 4.2.1.1`, `table LPC --page 15` |
| G29 | PWM fan control signal frequency and tachometer output | PWM-FAN Rev 1.3 | 4-Wire PWM Controlled Fans 1.3, sections 2.1.3 and 2.1.4, page 9: PWM target 25 kHz, acceptable 21 to 28 kHz, VIL 0.8 V, pulled up to at most 5.25 V in the fan (3.3 V encouraged); tachometer two pulses per revolution, open collector or open drain, pulled up to 12 V on the motherboard | `find PWM-FAN "PWM Frequency"`, `page PWM-FAN 9` |

## NVM Express

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G30 | Admin command opcodes: Get Log Page, Identify, Set Features, Get Features, Firmware Commit, NVMe-MI Send and Receive | NVME-BASE 2.4 | NVMe Base 2.4, section 5, Figure 143, pages 202-203: Get Log Page 02h, Identify 06h, Abort 08h, Set Features 09h, Get Features 0Ah, Asynchronous Event Request 0Ch, Firmware Commit 10h, Firmware Image Download 11h, NVMe-MI Send 1Dh, NVMe-MI Receive 1Eh | `find NVME-BASE "Opcodes for Admin Commands"`, `table NVME-BASE --page 202` |
| G31 | NVMe-MI message header: MCTP message type, and the NMIMT values | NVME-MI 2.2 | NVMe-MI 2.2, section 3.1.1, Figure 20, pages 41-42: MCTP message type 4h; NMIMT 0h Control Primitive, 1h NVMe-MI Command, 2h NVMe Admin Command, 4h PCIe Command, 5h Asynchronous Event; ROR bit 7 (0 request, 1 response), CSI bit 0 selects Command Slot 0 or 1 | `find NVME-MI NMIMT --version 2.2`, `page NVME-MI 41 --to 42 --version 2.2` |
| G32 | PCI configuration header of an NVMe controller: where the memory register BARs and the class code sit | NVME-PCIE 1.4 | NVMe over PCIe 1.4, section 3.8.1, Figure 10, page 17: MLBAR (BAR0) 10h-13h, MUBAR (BAR1) 14h-17h, BAR2 18h index/data pair or vendor specific, CC class code 09h-0Bh (BCC, SCC, PI in Figure 15, page 18) | `find NVME-PCIE MLBAR`, `table NVME-PCIE --page 17` |

## OCP DC-SCM and DC-MHS

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G33 | LTPI frame types, their comma symbols and size | LTPI Rev 1.2 Ver 1.0 | LTPI Rev 1.2 Ver 1.0, section 3, Table 19, PDF page 52 (printed 46): K28.5 Link Detect and Link Speed Selection, K28.6 Capabilities Advertise and Configure/Accept, K28.7 LTPI Operational Frame; every frame is 16 symbols (160 bits in 8b/10b); base frequency 25 MHz SDR (3.1.1.1, page 53) | `find LTPI "Frame Types summary"`, `page LTPI 52 --to 53` |
| G34 | M-CRPS 73.5 mm form factor dimensions and the sideband signals on its card edge | M-CRPS R1 v1.0 RC4 | M-CRPS v1.00 RC4, section 2.6.1, Tables 2-2 and 2-3, pages 34-35: 40 x 73.5 x 185 mm; signal pins A19-A25 / B19-B25: PMBus SDA, PMBus SCL, PSON#, SMBAlert#, Return Sense / PS_KILL, Remote sense, PWOK, A0 and A1 (SMBus address), +12VSB, Cold Redundancy Bus, 12V load share bus, Imon, VINOK | `section M-CRPS 2.6`, `page M-CRPS 34 --to 35` |
| G35 | Signals on the M-PIC primary control panel connector | M-PIC R1 v1.11 | M-PIC 1.11, section 11.4.1, Table 23, pages 81-82: 12V_CP and GND, [SMB/I3C]_BMC_SDA/SCL from the DC-SCM BMC, PCP_SB[4:1] sideband GPIOs from the HPM FPGA (SB1 suggested for PRES_N or PESTI, SB2 for PWREN), optional USB 2.0 USB_PCP_DP/DN, SPI from the DC-SCM; 2x10 header pinout in Table 24 | `find M-PIC "Control Panel Pin"`, `page M-PIC 81 --to 82` |
| G36 | Signals of an M-XIO port | M-XIO R1 v1.04 RC1 | M-XIO 1.04, section 6, Table 2, pages 13-14: PER/PET PCIe lanes, REFCLK_D 100 MHz, SMSCL/SMSDA (SMBus up to 400 kHz or I3C after discovery, BMC domain), PERST_N, CBL_PRES_PESTI_N (cable presence and PESTI), 3p3AUX_MGMT, GND, FLEXIO_[0:6], USB2 | `section M-XIO 6`, `table M-XIO --page 13` |
| G37 | M-DNO HPM board types and their widths | M-DNO R1 v1.1 RC2 | M-DNO Rev 1.0 Version 1.1, section 9, pages 20-21: Type 2 and Type 3 are half width (210 mm), Type 4 is three-quarter width (295 mm); Type 1 (full width) is defined by M-FLW; DC-SCM and OCP NIC connector locations are common to all types relative to the datum | `section M-DNO 9`, `page M-DNO 20 --to 21` |
| G38 | M-FLW HPM power zones and their ratings | M-FLW R1 v1.2 RC3 | M-FLW Rev 1.0 Version 1.2 RC3, section 11, Table 5, page 60: Zone A M-CRPS connector ingress up to 3200 W, Zone B 2x6+12s PICPWR egress up to 864 W, Zone C near side riser PICPWR up to 252 W per connector, Zone D DC-SCM R2.x up to 50 W, Zone E OCP NIC R3.0 and Platform Custom Zone up to 160 W | `section M-FLW 11`, `page M-FLW 60` |
| G39 | PESTI protocol commands and their data byte values | M-PESTI R1 v1.2 RC2 | M-PESTI 1.2 RC2, section 3.4, page 13: Discovery Payload Request 00h, Virtual Wire Exchange 01h (a target without virtual wires answers 00h), Mux Switch Command 02h for fanout devices | `section M-PESTI 3.4`, `page M-PESTI 13` |
| G40 | M-SDNO HPM classes and their widths | M-SDNO v1.1 RC2 | M-SDNO R1.0 V1.1 RC2, section 8.1, pages 22-23: Class A 19" half width 210 mm, Class B 21" half width 250 mm, Class C 19" full width 426 mm, Class D 21" full width 512 mm, Class E 19" full width 426 mm with M-CRPS direct dock; length is variable up to Common Chassis Intervals | `section M-SDNO 8.1`, `page M-SDNO 22 --to 23` |

## SMBus, CMIS, SGPIO and PMBus

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G41 | SMBus Alert Response Address and Device Default Address | SMBUS 3.3.1 | SMBus 3.3.1, sections 6.2.2.6 and 6.2.2.7, page 35: Alert Response Address 0001 100b (see Appendix A, SMBALERT#); Device Default Address 1100 001b, reserved for the Address Resolution Protocol | `find SMBUS "Alert Response Address"`, `page SMBUS 35` |
| G42 | CMIS Module State Machine states and exit-condition priority | CMIS 5.4 | OIF-CMIS 5.4, section 6.3.2.2, Figure 6-3 and Table 6-10, page 87: Reset, Resetting, MgmtInit, ModuleLowPwr, ModulePwrUp, ModuleReady, ModulePwrDn, Fault; power-up starts in Reset and moves to MgmtInit when ResetS is false; exit priority ResetS, then FaultS, then all others | `section CMIS 6.3.2.2`, `page CMIS 87`, `render CMIS --page 87` (the diagram is a figure) |
| G43 | SGPIO bus signals and who drives them | SFF-8485 Rev 0.7 | SFF-8485 Rev 0.7, section 5, Table 2, PDF page 11 (printed 10): SClock, SLoad (last clock of a bit stream) and SDataOut driven by the initiator, SDataIn by the target and optional; all transmitters open drain | `section SFF-8485 5`, `table SFF-8485 --page 11` |
| G44 | PMBus Group Command Protocol rules | PMBUS-I 1.3.1 | 1.5 is gated (sent on request), so 1.3.1 is the newest open version. PMBus Part I 1.3.1, section 5.6.1, page 13: mandatory; commands for several devices in one transmission separated by REPEATED START, one command per device, executed when all see the STOP; not for commands that return data (STATUS_BYTE); with PEC each sub-packet has its own PEC | `section PMBUS-I 5.6.1`, `page PMBUS-I 13` |
| G45 | PMBus command codes for STATUS_BYTE, STATUS_WORD, READ_VIN, READ_VOUT, READ_IOUT, READ_TEMPERATURE_1, PMBUS_REVISION | PMBUS-II 1.3.1 | 1.5 is gated (sent on request), so 1.3.1 is the newest open version. PMBus Part II 1.3.1, Appendix command summary, page 116: STATUS_BYTE 78h, STATUS_WORD 79h, READ_VIN 88h, READ_VOUT 8Bh, READ_IOUT 8Ch, READ_TEMPERATURE_1 8Dh, READ_FAN_SPEED_1 90h, READ_POUT 96h, PMBUS_REVISION 98h; READ_VOUT itself in 18.4, page 98 | `find PMBUS-II READ_VOUT`, `table PMBUS-II --page 116` (one Logical Table over pages 112-120) |

## MCTP transport bindings and message types

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G46 | PCIe Vendor ID and VDM message code that identify MCTP over PCIe VDM | DSP0238 1.4.0 | DSP0238 1.4.0, section 6.2.1 packet field table, page 12: Vendor ID 0x1AB4 (6836, DMTF), Message Code 0111_1111b (Type 1 VDM), MCTP VDM Code 0000b | `find DSP0238 1AB4`, `page DSP0238 12` |
| G47 | How an I3C Controller sends an MCTP packet to an I3C Target, and what follows the message data | DSP0233 1.0.1 | DSP0233 1.0.1, section 5.2.1, Figure 4 and Table 1, pages 15-16: a private write to the Target's dynamically assigned address carries the MCTP header and data, followed by a PEC byte (clause 5.3.1) | `section DSP0233 5.2`, `page DSP0233 16`, `render DSP0233 --page 16` |
| G48 | How an MCTP packet is framed on a serial link | DSP0253 1.0.0 | DSP0253 1.0.0, section 7, page 10: 0x7E flag first and last; 0x7E in the data becomes 0x7D 0x5E and 0x7D becomes 0x7D 0x5D; CRC-16 CCITT frame check; packet size is byte count + 4 | `find DSP0253 0x7E`, `page DSP0253 10` |
| G49 | Transport-specific MCTP control commands of the KCS binding | DSP0254 1.0.0 | DSP0254 1.0.0, section 7, Table 6, page 14: Register Endpoint 0xF0, Get MCTP Packet 0xF1, Enable MCTP SMS_ATN 0xF2 | `find DSP0254 "Register Endpoint"`, `table DSP0254 --page 14` |
| G50 | How a host finds an MCTP Host Interface in the SMBIOS tables | DSP0256 2.0.0 | DSP0256 2.0.0, section 9.1, Table 2, page 18: a Type 42 structure whose Interface Type is in the MCTP Host Interfaces range of DSP0239, with a Protocol Record of type MCTP (03h) carrying MCTP protocol version (WORD, 0x0103 for 1.3.1), link-layer type, instance number and characteristics | `find DSP0256 "Type 42"`, `page DSP0256 18`, `table DSP0256 --page 18` |
| G51 | USB interface descriptor values that identify an MCTP over USB interface | DSP0283 1.1.0 | DSP0283 1.1.0, section 6.2.1.1, Table 1, page 13: class 0x14, sub-class 0x0 (MC and managed device, no packet spanning; 0x1 host interface), protocol 0x1 (MCTP 1.x), two bulk endpoints; sub-class 0x2 with packet spanning in 6.2.2.1, page 15 | `find DSP0283 "Class code"`, `page DSP0283 13` |
| G52 | How an MCTP packet sits in an MMBI packet | DSP0284 1.0.1 | DSP0284 1.0.1, section 5.2, Table 1, page 10: MMBI packet type 0100b, header version 0001b, Null destination and source EIDs, padding to a 4-byte multiple | `find DSP0284 "Packet Type"`, `section DSP0284 5.2`, `page DSP0284 10` (Figure 1's rotated labels extract as single letters) |
| G53 | Layout of an MCTP message in an Extended PCC subspace | DSP0292 1.0.0 | DSP0292 1.0.0, sections 8.4 and 8.4.1, Figure 2, page 14: 16-byte header (PCC Signature, Flags, Length, Command = "MCTP", little-endian 0x5054434D), MCTP transport header at offset 16, message body from offset 20 | `find DSP0292 Signature`, `page DSP0292 14` |
| G54 | Which transport bindings NVMe Management Messages over MCTP are defined for, and where the message type number lives | DSP0235 1.0.1 | DSP0235 1.0.1, sections 7.1 and 7.2, page 9: DSP0237 (SMBus) and DSP0238 (PCIe); the number itself is assigned in DSP0239 (0x04, see G9) | `find DSP0235 "transport bindings"`, `page DSP0235 9` |
| G55 | MCTP message type of CXL FM API messages and their IC and TO bits | DSP0234 1.0.0 | DSP0234 1.0.0, section 7.4.1, Table 1, page 11: 0x07; IC 0b; TO 1b on requests and event notifications, 0b on responses | `find DSP0234 0x07`, `page DSP0234 11` |
| G56 | MCTP message type of CXL Type 3 CCI messages and the version reported | DSP0281 1.0.0 | DSP0281 1.0.0, sections 7.1 and 7.2, page 11: 0x08; version 1.0 reported as 0xF1F0FF00 | `find DSP0281 0x08`, `page DSP0281 11` |
| G57 | MCTP message type of PCIe-MI messages | DSP0291 1.0.0 | DSP0291 1.0.0, sections 9.1 and 9.2, page 13: 0x09; version 1.0 reported as 0xF1F0FF00 | `find DSP0291 "message type number"`, `page DSP0291 13` |

## PLDM companion specifications

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G58 | MCTP message type and IC bit of a PLDM message | DSP0241 1.0.0 | DSP0241 1.0.0, section 6.1, Table 1, page 8: PLDM = 0x01 (000_0001b), IC 0b | `find DSP0241 "Message Type"`, `page DSP0241 8` |
| G59 | PLDM File Transfer command codes and what DfOpen returns | DSP0242 1.0.1 | DSP0242 1.0.1, section 9, Table 6, page 27: DfOpen 0x01, DfClose 0x02, DfHeartbeat 0x03, DfProperties 0x10, DfGetFileAttribute 0x11, DfSetFileAttribute 0x12, DfRead 0x20 (MultipartReceive), DfFIFOSend 0x21 (MultipartSend); DfOpen returns the FileDescriptor used by DfRead, DfHeartbeat and DfClose (9.2, page 29) | `find DSP0242 "Command Codes"`, `table DSP0242 --page 27` |
| G60 | PLDM for SMBIOS Data Transfer command codes | DSP0246 1.0.1 | DSP0246 1.0.1, section 8.2, Table 3, page 11: GetSMBIOSStructureTableMetadata 0x01, SetSMBIOSStructureTableMetadata 0x02, GetSMBIOSStructureTable 0x03, SetSMBIOSStructureTable 0x04, GetSMBIOSStructureByType 0x05, GetSMBIOSStructureByHandle 0x06 | `find DSP0246 GetSMBIOSStructureTable`, `table DSP0246 --page 11` |
| G61 | PLDM for BIOS Control and Configuration command codes | DSP0247 1.0.0 | DSP0247 1.0.0, section 8, Table 31, page 35: GetBIOSTable 0x01, SetBIOSTable 0x02, UpdateBIOSTable 0x03, GetBIOSTableTags 0x04, SetBIOSTableTags 0x05, AcceptBIOSAttributesPendingValues 0x06, SetBIOSAttributeCurrentValue 0x07, GetBIOSAttributeCurrentValueByHandle 0x08, GetBIOSAttributePendingValueByHandle 0x09, GetBIOSAttributeCurrentValueByType 0x0a, GetBIOSAttributePendingValueByType 0x0b, GetDateTime 0x0c | `find DSP0247 GetBIOSTable`, `page DSP0247 35` |
| G62 | State set ID and values of Health State | DSP0249 1.4.0 | DSP0249 1.4.0, section 6.3, Table 1, page 12: set 1; 1 Normal/OK, 2 Non-Critical/Warning, 3 Critical, 4 Fatal, 5 Upper Non-Critical, 6 Lower Non-Critical, 7 Upper Critical, 8 Lower Critical, 9 Upper Fatal, 10 Lower Fatal | `find DSP0249 "Health State"`, `page DSP0249 12` |
| G63 | PLDM for FRU Data command codes | DSP0257 2.0.0 | DSP0257 2.0.0, section 13, Table 7, page 23: GetFRURecordTableMetadata 0x01, GetFRURecordTable 0x02, SetFRURecordTable 0x03, GetFRURecordByOption 0x04, ReadFRUDataItem 0x10, WriteFRUDataItem 0x11, FindFRUFiles 0x18, GetFRUFileMetadata 0x19 | `find DSP0257 "Command Codes"`, `page DSP0257 23`, `table DSP0257 --page 23` |
| G64 | RDE command codes | DSP0218 1.2.0 | DSP0218 1.2.0, section 10, Table 51, pages 111-113: NegotiateRedfishParameters 0x01, NegotiateMediumParameters 0x02, GetSchemaDictionary 0x03, GetSchemaURI 0x04, GetResourceETag 0x05, GetOEMCount 0x06 to GetSchemaFile 0x0C, RDEOperationInit 0x10, SupplyCustomRequestParameters 0x11, RetrieveCustomResponseParameters 0x12, RDEOperationComplete 0x13, RDEOperationStatus 0x14, RDEOperationKill 0x15, RDEOperationEnumerate 0x16, RDEMultipartSend 0x30, RDEMultipartReceive 0x31 | `find DSP0218 NegotiateMediumParameters`, `table DSP0218 --page 111` (one Logical Table over pages 111-113) |

## SPDM companion specifications

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G65 | MCTP message type of SPDM and the version it reports | DSP0275 1.0.2 | DSP0275 1.0.2, sections 4.5.1 and 4.7, page 9: SPDM = 0x05 (000_0101b), IC 0b; version 1.0.2 reported as 0xF1F0F200 | `find DSP0275 "message type"`, `page DSP0275 9`, `table DSP0275 --page 9` |
| G66 | MCTP message type of Secured Messages and the size of the Partial Sequence Number | DSP0276 2.0.0 | DSP0276 2.0.0, section 4, Figure 1, page 8: message type 6, IC 0; Partial Sequence Number is 2 bytes, the low 16 bits of the DSP0277 sequence number; in 2.0.0 the header also carries Attributes, LTD ID, LTD Segment Number and Protected Payload Offset | `find DSP0276 "message type 6"`, `page DSP0276 8` |
| G67 | Fields of a Secured Message | DSP0277 2.0.0 | DSP0277 2.0.0, section 7.1, Figure 1 and Table 1, pages 14-17: Session ID (4 bytes), Attributes (2, new in 2.0.0), Sequence Number (S bytes, set by the transport binding), Length (4), LTD ID (2), LTD Segment Number (4), Protected Payload Offset (2), LTD Segment Length (4), LTD Segment, Random Data, MAC; 1.3.0 had Application Data Length and Application Data where 2.0.0 has the Layered Transport Data fields | `find DSP0277 "Session ID"`, `page DSP0277 14 --to 17`, `table DSP0277 --page 15` (Table 1, pages 15-18) |
| G68 | SCSI SECURITY PROTOCOL value for SPDM and how the SPDM operation is passed | DSP0286 1.0.0 | DSP0286 1.0.0, sections 7.2.2.1 and 7.2.2.2, Tables 17 and 18, pages 33-34: SECURITY PROTOCOL 0xE8; SECURITY PROTOCOL SPECIFIC bits [1:0] ConnectionID, bits [7:2] SPDMOperation | `find DSP0286 0xE8`, `page DSP0286 33 --to 34` |
| G69 | TCP port assigned to SPDM | DSP0287 1.0.0 | DSP0287 1.0.0, section 5, page 9: IANA port 4194; one SPDM communication does not span TCP connections | `find DSP0287 4194` |
| G70 | Generic Authorization message header and how request and response codes are told apart | DSP0289 1.0.0 | DSP0289 1.0.0, section 9.1.6, Table 15, page 50: byte 0 RequestResponseCode (0x00 to 0x7F responses, 0x80 to 0xFF requests), byte 1 reserved, payload from byte 2; an unsupported request gets AUTH_ERROR with ErrorCode UnsupportedRequest | `section DSP0289 9.1.6`, `page DSP0289 50`, `table DSP0289 --page 50` |

## NC-SI

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G71 | EtherType of NC-SI Control Packets and the Get Link Status command and response codes | DSP0222 1.2.1 | DSP0222 1.2.1, section 8.1.1, Table 9, page 69: EtherType 0x88F8, destination address broadcast; sections 8.4.23 and 8.4.24, page 98: command 0x0A, response 0x8A | `find DSP0222 0x88F8`, `section DSP0222 8.4.23`, `page DSP0222 98` |
| G72 | MCTP message types used by NC-SI over MCTP | DSP0261 1.3.1 | DSP0261 1.3.1, section 5.3, Table 1, page 12: NC-SI Control 0x02, Ethernet (Pass-through) 0x03 | `find DSP0261 "Message types"`, `table DSP0261 --page 12` |
| G73 | How NC-SI is exposed over USB | DSP0296 1.0.0 | DSP0296 1.0.0, sections 8.1 and 8.2, page 11: the NCs are USB functions on a bus whose host controller is the MC, exposed as a CDC ECM or NCM subclass; up to eight packages with 31 channels each; an NC may share a composite device with an MCTP over USB (DSP0283) function | `section DSP0296 8.2`, `page DSP0296 11` |

## SMBIOS

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G74 | Which structures a compliant SMBIOS implementation must provide | DSP0134 3.9.0 | DSP0134 3.9.0, section 6.2, Table 4, pages 28-29: Firmware Information (Type 0), System Information (1), System Enclosure (3), Processor Information (4), Cache Information (7), System Slots (9), Physical Memory Array (16), Memory Device (17), Memory Array Mapped Address (19), System Boot Information (32) | `section DSP0134 6.2`, `table DSP0134 --page 28` (one Logical Table over pages 28-29) |

## Redfish documents

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G75 | Properties every Redfish resource carries, and which are required | DSP0268 2026.1 | DSP0268 2026.1, section 3.1.1, page 13: @odata.context, @odata.etag, @odata.id (required), @odata.type (required), Description, Id (required), Name (required), Oem | `section DSP0268 3.1`, `page DSP0268 13`, `table DSP0268 --page 13` |
| G76 | Values of the Sensor resource's ReadingType | DSP2046 2026.1 | DSP2046 2026.1, section 6.124.5.7, pages 971-973: AbsoluteHumidity, AirFlow (deprecated v1.7), AirFlowCMM, Altitude, Barometric, ChargeAh, Current, EnergyJoules and the rest of the list through Voltage; the property itself in 6.124.3, page 964 | `section DSP2046 6.124.5.7`, `page DSP2046 971 --to 973`, `table DSP2046 --page 971` (the ReadingType values table runs over pages 971-972) |
| G77 | How the Redfish host interface is described in SMBIOS and which device types it allows | DSP0270 1.3.1 | DSP0270 1.3.1, sections 7.2 and 7.3.1, pages 15-16: Type 42 with interface type 40h (network host interface); device type 02h USB, 03h PCI/PCIe, 04h USB v2, 05h PCI/PCIe v2, 80h-FFh OEM | `find DSP0270 "Type 42"`, `section DSP0270 7.3.1`, `page DSP0270 15 --to 16`, `table DSP0270 --page 15` |
| G78 | ReadRequirement values in an interoperability profile and the default | DSP0272 1.10.0 | DSP0272 1.10.0, section 8.4.3.3, page 28: Mandatory (default), Supported, Recommended, IfImplemented, IfPopulated, Conditional | `section DSP0272 8.4.3.3`, `page DSP0272 28`, `table DSP0272 --page 28` |
| G79 | Which schemas define a PowerState property | DSP2053 2026.1 | DSP2053 2026.1, section 3 reference guide, page 216: Chassis, Manager, Processor, Switch, ComputerSystem, Circuit, OutletGroup, Outlet (also as an action parameter of BreakerControl and PowerControl) | `find DSP2053 PowerState`, `page DSP2053 216`, `table DSP2053 --page 216` (the guide is one table over pages 8-323; only the rows starting on page 216 are printed, after a `note:` line) |
| G80 | Severity, message text and resolution of Base.PropertyValueNotInList | DSP2065 2026.1 | DSP2065 2026.1, section 2.3.78, page 63: Warning; "The value '<1>' for the property <2> is not in the list of acceptable values."; resolution: choose a value from the enumeration list and resubmit; version added v1.0 | `find DSP2065 PropertyValueNotInList`, `page DSP2065 63` |

## OCP Security and OCP NIC

Rows G81 onwards were added in M10, one per document of the second round
of publishers (OCP Security and NIC, SNIA SFF, NIST, Arm, TCG, UEFI
Forum). TCG and UEFI Forum documents come from the Internet Archive; the
version is the one on the cover of the archived file.

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G81 | Which signature algorithms Caliptra accepts for firmware images | CALIPTRA 2.0 | CALIPTRA 2.0, section 4.5.13, pages 67-68: ECDSA over a SHA-384 image hash, optionally LMS (LMS_SHA256_M24_H15 with LMOTS_SHA256_N24_W4, 32 vendor trees and 1 owner tree) for CNSA 2.0, and from 2.0 optionally ML-DSA-87 (FIPS 204) alongside ECDSA | `find CALIPTRA "ML-DSA"`, `page CALIPTRA 67 --to 68` |
| G82 | What an attester device must support of SPDM | OCP-ATTEST 1.0 | OCP-ATTEST 1.0, sections 8.5.1 and 8.5.2, page 25: certificate digests and certificates on request, signed challenge responses (optional in SPDM, required here), the capabilities of the "Required Capabilities for SPDM" table, SPDM 1.0 or higher (items 2, 10-13) | `find OCP-ATTEST SPDM`, `page OCP-ATTEST 25` (the PDF has no bookmarks, so `section` has nothing to search) |
| G83 | SMBus address of the FRU EEPROM on an OCP NIC 3.0 card | OCP-NIC 1.6.0 | OCP-NIC 1.6.0, section 5.9.1, Table 64, page 197, lines 3883-3899: 8-bit addresses 0xA0/0xA1 (slot 0), 0xA4/0xA5 (slot 1), 0xA8/0xA9 (slot 2), 0xAC/0xAD (slot 3); A2 and A1 follow SLOT_ID[1:0] on pins OCP_A6 and OCP_B7, A0 is fixed 0 | `find OCP-NIC "FRU EEPROM"`, `table OCP-NIC --page 197` |

## SFF module management

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G84 | Meaning of the Diagnostic Monitoring Type bits (A0h byte 92) | SFF-8472 Rev 12.5a | SFF-8472 Rev 12.5a, sections 8.8 and 8.9, pages 32-33: bit 6 digital diagnostics implemented (then temperature, supply voltage, bias, transmit and receive power monitors and the A2h thresholds at bytes 0-55 are all mandatory), bit 5 internally calibrated, bit 4 externally calibrated (A/D counts, calibration constants at A2h bytes 56-95), bit 3 received power is average (set) or OMA (clear), bit 2 an address change sequence is needed before A2h | `find SFF-8472 "Byte 92"`, `page SFF-8472 32 --to 33` |
| G85 | Where the module temperature and supply voltage monitors are | SFF-8636 Rev 2.12 | SFF-8636 Rev 2.12, section 6.2.4 Free Side Device Monitors, page 36: Page 00h bytes 22-23 temperature MSB/LSB, bytes 26-27 supply voltage MSB/LSB | `find SFF-8636 "Temperature MSB"`, `page SFF-8636 36` |
| G86 | Identifier values of SFP, QSFP, QSFP+, QSFP28, QSFP-DD, OSFP and CMIS modules | SFF-8024 Rev 4.14 | SFF-8024 Rev 4.14, section 4.2 Transceiver References, pages 16-17: 03h SFP/SFP+/SFP28 (SFF-8472), 0Ch QSFP, 0Dh QSFP+ (SFF-8636 or SFF-8436), 11h QSFP28 (SFF-8636), 18h QSFP-DD, 19h OSFP, 1Eh QSFP+ or later with CMIS | `find SFF-8024 "QSFP-DD"`, `page SFF-8024 16 --to 17` |

## NIST and Arm

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G87 | The three roots of trust of SP 800-193 and what each is responsible for | SP800-193 2018 | SP800-193 2018, sections 4.1 to 4.1.4, pages 27-29: the Root of Trust for Update (RTU) authenticates firmware updates, the Root of Trust for Detection (RTD) detects corruption of firmware and critical data, the Root of Trust for Recovery (RTRec) recovers them; each may anchor a Chain of Trust (CTU, CTD, CTRec). The rotated "available free of charge" margin text of this PDF extracts as stray characters at the start of lines | `section SP800-193 4.1`, `page SP800-193 27 --to 28` |
| G88 | Which in-band host interfaces SBMR lists between the host SoC and the BMC | SBMR 3.0 | SBMR 3.0, section 1.3.1, page 19: IPMI SSIF Host Interface, Redfish Host Interface, MCTP Host Interface over an in-band medium such as MMBI; Table 2 maps the use cases (SMBIOS table, boot progress, event log, BIOS settings) to the three | `find SBMR SSIF`, `page SBMR 19` |
| G89 | What SBSA requires of the watchdog | SBSA 8.0 | SBSA 8.0, section 1.2.7, page 23: RS_L3WD_01, a base server system must implement a Non-secure Generic Watchdog; RS_L6WD_01, its architecture version must be v1 (W_IIDR[19:16] == 0001b), because v0 at 1 GHz limits the refresh period to about 4 seconds | `find SBSA "Generic Watchdog"`, `page SBSA 23` |
| G90 | The BBR recipes and which operating systems require SBBR | BBR 2.2 | BBR 2.2, sections 3 to 3.2, pages 8-10: SBBR, EBBR and LBBR; SBBR is sections 4 to 8 (UEFI, ACPI, SMBIOS and the rest) and is required by Windows Server, Windows 11, Windows IoT Enterprise, VMware ESXi, Amazon Linux and Oracle Linux; EBBR is the reduced UEFI environment, typically U-Boot | `find BBR SBBR`, `page BBR 10` |

## TCG

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G91 | Which algorithms the TPM 2.0 Library marks deprecated | TPM2-P0 185 | TPM2-P0 185, section 3.1.1, page 23: TPM_ALG_TDES and TPM_ALG_SHA1, deprecated in version 184 (SHA1 is withdrawn by NIST on 1 January 2031); the four parts are searched together, so `find` lists the other parts' hits as well | `find TPM2-P0 SHA1`, `page TPM2-P0 23` |
| G92 | Which hierarchy holds sequence objects and sessions, and whether its objects can be persistent | TPM2-P1 185 | TPM2-P1 185, sections 11.4.5 (page 84), 27.2.4 (page 216) and 34.3 (page 254): the NULL hierarchy; its objects cannot be made persistent | `find TPM2-P1 "Null Hierarchy"`, `page TPM2-P1 84` |
| G93 | TPM_ALG_ID values of RSA, ECC, SHA1, SHA256, SHA384 and SHA512, and the command codes of TPM2_Startup and TPM2_PCR_Extend | TPM2-P2 185 | TPM2-P2 185, section 6.3, page 42: 0x0001, 0x0023, 0x0004 (deprecated, see Part 0), 0x000B, 0x000C, 0x000D; section 6.5.2, pages 49 and 51: TPM_CC_Startup 0x00000144, TPM_CC_PCR_Extend 0x00000182 | `find TPM2-P2 TPM_ALG_SHA256`, `page TPM2-P2 42`, `find TPM2-P2 "TPM_CC_Startup "` |
| G94 | Layout of the TPM2_PCR_Extend command | TPM2-P3 185 | TPM2-P3 185, section 22.2.2, Tables 130 and 131, page 194: tag TPM_ST_SESSIONS, commandCode TPM_CC_PCR_Extend {NV}, handle @pcrHandle of type TPMI_DH_PCR+ (Auth Index 1, Auth Role USER), parameter digests of type TPML_DIGEST_VALUES; the response carries tag, responseSize and responseCode only | `find TPM2-P3 TPM_CC_PCR_Extend`, `page TPM2-P3 194` |
| G95 | Event type values of EV_SEPARATOR, EV_S_CRTM_CONTENTS and EV_S_CRTM_VERSION, and which PCRs they go to | TCG-PFP 1.06 Revision 52 | TCG-PFP 1.06 Revision 52, section 10.4.1 Event Types, pages 126-130 (the table spans the pages): 0x00000004 EV_SEPARATOR for PCRs 0 to 7, 0x00000007 EV_S_CRTM_CONTENTS and 0x00000008 EV_S_CRTM_VERSION for PCR[0] only; 0x00000001 EV_POST_CODE is deprecated as of PFP 1.06 | `find TCG-PFP EV_S_CRTM_VERSION`, `page TCG-PFP 128 --to 130` |
| G96 | How the Compound Device Identifier is derived | DICE-HW 1.0 Revision 0.91 | DICE-HW 1.0 Revision 0.91, section 4, page 8: by a one-way function from the Unique Device Secret and the TCB Component Identifier (the measurement of the First Mutable Code); the DICE alone reads the UDS after reset and before handing control to the FMC, so a change to the UDS or to any measured component changes the CDI (Figure 1 is a figure). The PDF has no bookmarks; the outline comes from the contents page | `find DICE-HW "Unique Device Secret"`, `page DICE-HW 8` |
| G97 | Fields of the DiceTcbInfo certificate extension | DICE-ATT 1.2 | DICE-ATT 1.2, section 6.1.1, pages 26-27: vendor [0], model [1], version [2], svn [3], layer [4], index [5], fwids [6], flags [7], vendorInfo [8], type [9], all OPTIONAL; an AuthorityKeyIdentifier extension MUST accompany it | `find DICE-ATT DiceTcbInfo`, `page DICE-ATT 26 --to 27` |

## UEFI Forum

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G98 | Numeric values of EFI_SUCCESS, EFI_LOAD_ERROR, EFI_INVALID_PARAMETER, EFI_UNSUPPORTED, EFI_NOT_FOUND and EFI_ACCESS_DENIED | UEFI 2.11 | UEFI 2.11, Appendix D Status Codes, pages 2068-2069: 0, 1, 2, 3, 14, 15 (error codes carry the high bit of EFI_STATUS set) | `find UEFI EFI_LOAD_ERROR`, `page UEFI 2068 --to 2069` |
| G99 | The PCC subspace structure types | ACPI 6.6 | ACPI 6.6, sections 14.1.2 and 14.1.3, pages 870-871: type 0 Generic Communications Subspace, types 1 and 2 HW-Reduced Communications Subspaces, types 3 and 4 extended PCC subspaces, type 5 Hardware Register-Based PCC Subspace | `find ACPI "Generic Communications Subspace"`, `page ACPI 870` |
| G100 | HOB type values | PI 1.10 | PI 1.10, section III-5.3 PHIT HOB, page 482: EFI_HOB_TYPE_HANDOFF 0x0001, MEMORY_ALLOCATION 0x0002, RESOURCE_DESCRIPTOR 0x0003, GUID_EXTENSION 0x0004, FV 0x0005, CPU 0x0006, MEMORY_POOL 0x0007, FV2 0x0009, LOAD_PEIM_UNUSED 0x000A, UEFI_CAPSULE 0x000B, FV3 0x000C, RESOURCE_DESCRIPTOR2 0x000D, UNUSED 0xFFFE, END_OF_HOB_LIST 0xFFFF | `find PI EFI_HOB_TYPE_HANDOFF`, `page PI 482` |

## Redfish bundles

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G101 | Severity, text, arguments and resolution of Base.PropertyValueTypeError, as the registry states them | DSP8011 2026.1 | DSP8011 2026.1, Base 1.23.0, `#/Messages/PropertyValueTypeError`: MessageId `Base.1.23.PropertyValueTypeError`, severity Warning, two arguments; the text, verbatim: "The value '%1' for the property %2 is not a type that the property can accept."; %1 is the value provided, %2 the property name; resolution: correct the value for the property in the request body and resubmit the request if the operation failed | `extract DSP8011`, `registry DSP8011 Base PropertyValueTypeError` |
| G102 | What a property entry of an interoperability profile may specify | DSP8013 2026.1 | DSP8013 2026.1, RedfishInteroperabilityProfile v1.10.0, `#/definitions/PropertyProfile`: ReadRequirement and WriteRequirement (enums), ReplacedByProperty, ReplacesProperty, Priority, Purpose, MinCount, MinSupportValues, Comparison, Values, ConditionalRequirements and nested PropertyRequirements; ReadRequirement takes Mandatory, Supported, Recommended, IfImplemented, IfPopulated, Conditional or None, Mandatory being the default when absent (`#/definitions/ReadRequirement`) | `extract DSP8013`, `schema DSP8013 RedfishInteroperabilityProfile --definition PropertyProfile`, `schema DSP8013 RedfishInteroperabilityProfile --definition ReadRequirement` |

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
| DSP0239 Table 1 MCTP Message Types (cell boxes, no ruling lines) | `table DSP0239 --page 13` | one Logical Table, pages 13-14, 14 rows; the `table:` line says `cells (no ruling lines)` |
| DSP0274 Table 4 SPDM request codes (cell boxes) | `table DSP0274 --page 39` | pages 39-41, 32 rows, the header repeated on each page dropped |
| DSP2053 the property guide (one cell-box table over the whole document) | `table DSP2053 --page 216` | a `note:` line, then only the rows that start on page 216; `--all-rows` prints all 4251 |

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
