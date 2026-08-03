"""Parsing for CanadaBuys CSV field formats.

Isolated here because these are feed trivia that will churn; the rest of the
system should never need to know about star prefixes or missing timezones.
"""
import datetime

# The feed publishes naive timestamps in UTC-0500. See url-reference.md.
FEED_TZ = datetime.timezone(datetime.timedelta(hours=-5))

COL_TITLE = "title-titre-eng"
COL_REF = "referenceNumber-numeroReference"
COL_AMENDMENT = "amendmentNumber-numeroModification"
COL_SOLICITATION = "solicitationNumber-numeroSollicitation"
COL_PUBLISHED = "publicationDate-datePublication"
COL_CLOSING = "tenderClosingDate-appelOffresDateCloture"
COL_AMENDED_DATE = "amendmentDate-dateModification"
COL_STATUS = "tenderStatus-appelOffresStatut-eng"
COL_GSIN = "gsin-nibs"
COL_GSIN_DESC = "gsinDescription-nibsDescription-eng"
COL_UNSPSC = "unspsc"
COL_UNSPSC_DESC = "unspscDescription-eng"
COL_CATEGORY = "procurementCategory-categorieApprovisionnement"
COL_NOTICE_TYPE = "noticeType-avisType-eng"
COL_PROC_METHOD = "procurementMethod-methodeApprovisionnement-eng"
COL_SELECTION = "selectionCriteria-criteresSelection-eng"
COL_REGIONS_DELIVERY = "regionsOfDelivery-regionsLivraison-eng"
COL_REGIONS_OPPORTUNITY = "regionsOfOpportunity-regionAppelOffres-eng"
COL_ENTITY = "contractingEntityName-nomEntitContractante-eng"
COL_END_USER = "endUserEntitiesName-nomEntitesUtilisateurFinal-eng"
COL_DESCRIPTION = "tenderDescription-descriptionAppelOffres-eng"
COL_DESCRIPTION_FR = "tenderDescription-descriptionAppelOffres-fra"
COL_NOTICE_URL = "noticeURL-URLavis-eng"
COL_ATTACHMENT = "attachment-piecesJointes-eng"
COL_CONTACT_NAME = "contactInfoName-informationsContactNom"
COL_CONTACT_EMAIL = "contactInfoEmail-informationsContactCourriel"


def split_multi(raw: str | None) -> list[str]:
    """Split a `*`-prefixed, newline-separated multi-value field.

    "*12160000\\n*12350000" -> ["12160000", "12350000"]
    "*Canada"               -> ["Canada"]
    """
    if not raw:
        return []
    parts = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return [p.lstrip("*").strip() for p in parts if p.strip().strip("*")]


def parse_date(raw: str | None) -> datetime.date | None:
    if not raw or not raw.strip():
        return None
    return datetime.date.fromisoformat(raw.strip())


def parse_datetime(raw: str | None) -> datetime.datetime | None:
    """Parse a naive feed timestamp and attach the feed's timezone.

    Returning tz-aware values is deliberate: deadline arithmetic against a
    naive datetime silently computes in local time and can be hours wrong.
    """
    if not raw or not raw.strip():
        return None
    return datetime.datetime.fromisoformat(raw.strip()).replace(tzinfo=FEED_TZ)
