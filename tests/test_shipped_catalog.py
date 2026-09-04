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
    # M8a
    "LPC",
    "PWM-FAN",
    "LTPI",
    "SFF-8485",
    "PMBUS-I",
    "PMBUS-II",
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
    # Wayback documents keep the URL the Internet Archive indexed, which for
    # a site that died before TLS is http://; gated versions carry no URL.
    bad = [
        (d.id, v.version)
        for d in shipped.documents
        if d.fetch != "manual"
        for v in d.versions
        if v.open
        and not v.url.startswith(
            "https://" if d.fetch == "direct" else ("https://", "http://")
        )
    ]
    assert not bad


def test_gated_versions_carry_no_url_and_an_open_sibling(shipped):
    gated = [(d, v) for d in shipped.documents for v in d.versions if not v.open]
    assert gated, "M8a lists PMBus 1.4 and 1.5 as gated"
    assert all(v.url == "" for _, v in gated)
    assert all(d.newest_open() is not None for d, _ in gated)


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


# ---------------------------------------------------------- M8 follow-ups


def test_latest_does_not_depend_on_the_order_of_the_version_entries(shipped):
    import dataclasses

    from bmc_toolkit.spec.catalog import version_numbers

    for doc in shipped.documents:
        if not doc.versions:
            continue
        reversed_doc = dataclasses.replace(doc, versions=tuple(reversed(doc.versions)))
        assert doc.latest() == reversed_doc.latest(), doc.id
        assert doc.newest_open() == reversed_doc.newest_open(), doc.id
        # every same-day pair is told apart by its version numbers
        for date in {v.published for v in doc.versions}:
            keys = [
                version_numbers(v.version) for v in doc.versions if v.published == date
            ]
            assert len(keys) == len(set(keys)), (doc.id, date)


def test_versions_are_listed_in_publication_order_then_version_order(shipped):
    # The convention `refresh --write` follows: a version block goes after
    # the ones published before it; same-day releases (DMTF publishes the
    # errata of several branches together) ascend by version number.
    from bmc_toolkit.spec.catalog import version_numbers

    def order(doc):
        return [(v.published, version_numbers(v.version)) for v in doc.versions]

    bad = [
        (d.id, [v.version for v in d.versions])
        for d in shipped.documents
        if order(d) != sorted(order(d))
    ]
    assert not bad, bad
    dsp0277 = [v.version for v in shipped.get("DSP0277").versions]
    assert dsp0277.index("1.0.1") < dsp0277.index("1.1.1")
    assert shipped.get("DSP0277").latest().version == "2.0.0"
    assert shipped.get("DSP0276").latest().version == "2.0.0"
