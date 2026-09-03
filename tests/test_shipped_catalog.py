"""The catalog shipped in the repository covers the v1 scope and is well-formed."""

import pytest

from bmc_toolkit.spec.catalog import load_catalog

V1_DOCUMENTS = [
    # Intel
    "IPMI",
    "IPMI-UPDATE",
    "IPMB",
    "IPMI-FRU",
    "DCMI",
    "ESPI",
    # DMTF MCTP
    "DSP0236",
    "DSP0237",
    "DSP0238",
    "DSP0239",
    "DSP0233",
    "DSP0253",
    "DSP0254",
    "DSP0256",
    "DSP0283",
    "DSP0284",
    "DSP0292",
    "DSP0235",
    "DSP0234",
    "DSP0281",
    "DSP0291",
    # DMTF PLDM
    "DSP0240",
    "DSP0241",
    "DSP0242",
    "DSP0245",
    "DSP0246",
    "DSP0247",
    "DSP0248",
    "DSP0249",
    "DSP0257",
    "DSP0267",
    "DSP0218",
    # DMTF SPDM
    "DSP0274",
    "DSP0275",
    "DSP0276",
    "DSP0277",
    "DSP0286",
    "DSP0287",
    "DSP0289",
    # NC-SI, SMBIOS
    "DSP0222",
    "DSP0261",
    "DSP0296",
    "DSP0134",
    # Redfish
    "DSP0266",
    "DSP8010",
    "DSP0268",
    "DSP2046",
    "DSP0270",
    "DSP0272",
    "DSP8011",
    # NVMe
    "NVME-BASE",
    "NVME-MI",
    # OCP
    "DC-SCM",
    "M-CRPS",
    "M-PIC",
    "M-XIO",
    "M-DNO",
    "M-FLW",
    # Buses
    "UM10204",
    "SMBUS",
    "CMIS",
]


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def test_every_v1_document_is_present_with_a_published_version(shipped):
    missing = [d for d in V1_DOCUMENTS if shipped.get(d) is None]
    assert not missing, f"missing from catalog: {missing}"
    unpublished = [d for d in V1_DOCUMENTS if shipped.get(d).latest() is None]
    assert not unpublished, f"no published version: {unpublished}"


def test_every_fetchable_version_has_an_https_url(shipped):
    bad = [
        (d.id, v.version)
        for d in shipped.documents
        if d.fetch != "manual"
        for v in d.versions
        if not v.url.startswith("https://")
    ]
    assert not bad


def test_confidential_documents_are_manual(shipped):
    bad = [
        d.id
        for d in shipped.documents
        if d.access == "confidential" and d.fetch != "manual"
    ]
    assert not bad


def test_document_ids_are_path_safe(shipped):
    import re

    bad = [
        d.id for d in shipped.documents if not re.fullmatch(r"[A-Za-z0-9._-]+", d.id)
    ]
    assert not bad


def test_ipmi_is_searched_with_its_update(shipped):
    assert shipped.get("IPMI").searched_with == ("IPMI-UPDATE",)
    assert shipped.get("IPMI-UPDATE") is not None
