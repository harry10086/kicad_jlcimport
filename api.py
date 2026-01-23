"""EasyEDA/LCSC HTTP client using only urllib."""
import json
import re
import ssl
import urllib.request
import warnings
from typing import Any, Dict, List, Optional


def _make_ssl_contexts():
    """Create verified and unverified SSL contexts.

    Returns (verified_ctx, unverified_ctx). The verified context is preferred;
    the unverified context is the fallback for KiCad's bundled Python where
    certificate stores may be missing or incomplete.
    """
    try:
        verified = ssl.create_default_context()
    except Exception:
        verified = None
    unverified = ssl._create_unverified_context()
    return verified, unverified


_SSL_VERIFIED, _SSL_UNVERIFIED = _make_ssl_contexts()
# Tracks whether we've already fallen back to unverified for this session
_ssl_use_unverified = False


def validate_lcsc_id(lcsc_id: str) -> str:
    """Validate and normalize an LCSC part number.

    Raises ValueError if the ID doesn't match the expected C<digits> format.
    """
    lcsc_id = lcsc_id.strip().upper()
    if not lcsc_id.startswith("C"):
        lcsc_id = "C" + lcsc_id
    if not re.match(r'^C\d{1,12}$', lcsc_id):
        raise ValueError(f"Invalid LCSC part number: {lcsc_id}")
    return lcsc_id


EASYEDA_API = "https://easyeda.com/api"
EASYEDA_3D_BUCKET = "https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y"
EASYEDA_3D_API = "https://easyeda.com/analyzer/api/3dmodel"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JLCImport/1.0)",
    "Accept": "application/json",
}


class APIError(Exception):
    """Raised when an API call fails."""
    pass


def _urlopen(req, timeout=30):
    """Open a URL with SSL fallback.

    Tries verified SSL first. If that fails with an SSL-related error,
    falls back to unverified SSL for the remainder of the session
    (common with KiCad's bundled Python on macOS/Windows).
    """
    global _ssl_use_unverified
    if not _ssl_use_unverified and _SSL_VERIFIED is not None:
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=_SSL_VERIFIED)
        except (urllib.error.URLError, ssl.SSLError, OSError) as e:
            # Check if this is SSL-related
            reason = getattr(e, 'reason', e)
            if isinstance(reason, (ssl.SSLError, OSError)) or 'ssl' in str(e).lower():
                _ssl_use_unverified = True
            else:
                raise
    return urllib.request.urlopen(req, timeout=timeout, context=_SSL_UNVERIFIED)


def _get_json(url: str) -> Any:
    """Fetch JSON from a URL."""
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with _urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise APIError(f"HTTP {e.code} fetching {url}") from e
    except urllib.error.URLError as e:
        raise APIError(f"Network error fetching {url}: {e.reason}") from e
    return data


def fetch_component_uuids(lcsc_id: str) -> List[Dict[str, Any]]:
    """Get component UUIDs from LCSC part number.

    Returns list of dicts with 'component_uuid' keys.
    Last entry is footprint, earlier entries are symbol parts.
    """
    url = f"{EASYEDA_API}/products/{lcsc_id}/svgs"
    data = _get_json(url)
    if not data.get("success") or not data.get("result"):
        raise APIError(f"No component found for {lcsc_id}")
    return data["result"]


def fetch_component_data(uuid: str) -> Dict[str, Any]:
    """Get component shape data by UUID."""
    url = f"{EASYEDA_API}/components/{uuid}"
    data = _get_json(url)
    if not data.get("result"):
        raise APIError(f"No data for component UUID {uuid}")
    return data["result"]


JLCPCB_SEARCH_API = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"


def search_components(keyword: str, page: int = 1, page_size: int = 10,
                      part_type: Optional[str] = None) -> Dict[str, Any]:
    """Search JLCPCB parts library.

    Args:
        keyword: Search term
        page: Page number (1-based)
        page_size: Results per page
        part_type: Filter by "base" or "expand" (None = all)

    Returns dict with 'total' and 'results' list. Each result has:
        lcsc, name, model, brand, package, category, stock, type, price, description
    """
    payload = {
        "keyword": keyword,
        "currentPage": page,
        "pageSize": page_size,
    }
    if part_type:
        payload["componentLibraryType"] = part_type

    data = json.dumps(payload).encode()
    req = urllib.request.Request(JLCPCB_SEARCH_API, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": _HEADERS["User-Agent"],
    })
    try:
        with _urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        raise APIError(f"Search failed: {e}") from e

    page_info = raw.get("data", {}).get("componentPageInfo", {})
    total = page_info.get("total", 0)
    items = page_info.get("list", [])

    results = []
    for item in items:
        prices = item.get("componentPrices", [])
        unit_price = prices[0]["productPrice"] if prices else None
        results.append({
            "lcsc": item.get("componentCode", ""),
            "name": item.get("componentName", ""),
            "model": item.get("componentModelEn", ""),
            "brand": item.get("componentBrandEn", ""),
            "package": item.get("componentSpecificationEn", ""),
            "category": item.get("componentTypeEn", ""),
            "stock": item.get("stockCount", 0),
            "type": "Basic" if item.get("componentLibraryType") == "base" else "Extended",
            "price": unit_price,
            "description": item.get("describe", ""),
            "url": item.get("lcscGoodsUrl", ""),
            "datasheet": item.get("dataManualUrl", ""),
        })

    return {"total": total, "results": results}


def filter_by_min_stock(results: list, min_stock: int) -> list:
    """Filter search results by minimum stock count.

    Args:
        results: List of result dicts from search_components()
        min_stock: Minimum stock threshold (0 means no filter)

    Returns filtered list (original list unchanged).
    """
    if min_stock <= 0:
        return list(results)
    return [r for r in results if r.get('stock') and r['stock'] >= min_stock]


def filter_by_type(results: list, part_type: str) -> list:
    """Filter search results by part type.

    Args:
        results: List of result dicts from search_components()
        part_type: "Basic", "Extended", or None/empty for all

    Returns filtered list (original list unchanged).
    """
    if not part_type:
        return list(results)
    return [r for r in results if r.get('type') == part_type]


_ALLOWED_IMAGE_HOSTS = ("jlcpcb.com", "www.jlcpcb.com", "lcsc.com", "www.lcsc.com")


def fetch_product_image(lcsc_url: str) -> Optional[bytes]:
    """Fetch product image from LCSC/JLCPCB product page. Returns JPEG bytes or None."""
    if not lcsc_url:
        return None
    # SSRF protection: only allow fetching from known LCSC/JLCPCB domains
    try:
        from urllib.parse import urlparse
        parsed = urlparse(lcsc_url)
        if parsed.hostname not in _ALLOWED_IMAGE_HOSTS:
            return None
        if parsed.scheme not in ("http", "https"):
            return None
    except Exception:
        return None

    req = urllib.request.Request(lcsc_url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })
    try:
        with _urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None

    # Find product image URL
    match = re.search(r'https://assets\.lcsc\.com/images/lcsc/900x900/[^\s"<>]+', html)
    if not match:
        return None

    img_url = match.group(0)
    if not img_url.startswith("https://assets.lcsc.com/"):
        return None
    req2 = urllib.request.Request(img_url, headers=_HEADERS)
    try:
        with _urlopen(req2, timeout=10) as resp:
            return resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def download_step(uuid_3d: str) -> Optional[bytes]:
    """Download STEP file binary for a 3D model UUID."""
    url = f"{EASYEDA_3D_BUCKET}/{uuid_3d}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with _urlopen(req, timeout=60) as resp:
            return resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def download_wrl_source(uuid_3d: str) -> Optional[str]:
    """Download OBJ-like text source for WRL conversion."""
    url = f"{EASYEDA_3D_API}/{uuid_3d}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with _urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def fetch_full_component(lcsc_id: str) -> Dict[str, Any]:
    """High-level: fetch all data needed for a component.

    Returns dict with keys:
        title, prefix, lcsc_id, datasheet,
        symbol_uuids, footprint_uuid,
        symbol_data (list of shape data dicts),
        footprint_data (shape data dict),
        description, manufacturer, manufacturer_part
    """
    lcsc_id = validate_lcsc_id(lcsc_id)
    uuids = fetch_component_uuids(lcsc_id)

    # Last UUID is footprint, others are symbol parts
    footprint_uuid = uuids[-1]["component_uuid"]
    symbol_uuids = [u["component_uuid"] for u in uuids[:-1]]

    # Fetch footprint data (from the footprint UUID)
    fp_data = fetch_component_data(footprint_uuid)

    # Fetch symbol data (from first symbol UUID - contains packageDetail too)
    sym_data_list = []
    for suuid in symbol_uuids:
        sym_data_list.append(fetch_component_data(suuid))

    # Primary symbol data has the main metadata
    primary = sym_data_list[0] if sym_data_list else fp_data

    # Extract metadata from primary symbol's c_para
    c_para = {}
    if sym_data_list:
        c_para = primary.get("dataStr", {}).get("head", {}).get("c_para", {})

    # Fallback to footprint head c_para
    fp_c_para = fp_data.get("dataStr", {}).get("head", {}).get("c_para", {})

    prefix = c_para.get("pre", fp_c_para.get("pre", "U?"))
    if prefix.endswith("?"):
        prefix = prefix[:-1]

    datasheet = c_para.get("link", fp_c_para.get("link", ""))
    if datasheet and not datasheet.startswith("http"):
        datasheet = "https:" + datasheet if datasheet.startswith("//") else ""

    # 3D model UUID from footprint head
    uuid_3d = fp_data.get("dataStr", {}).get("head", {}).get("uuid_3d", "")

    return {
        "title": primary.get("title", fp_data.get("title", lcsc_id)),
        "prefix": prefix,
        "lcsc_id": lcsc_id,
        "datasheet": datasheet,
        "description": primary.get("description", ""),
        "manufacturer": c_para.get("Manufacturer", ""),
        "manufacturer_part": c_para.get("Manufacturer Part", ""),
        "symbol_uuids": symbol_uuids,
        "footprint_uuid": footprint_uuid,
        "symbol_data_list": sym_data_list,
        "footprint_data": fp_data,
        "uuid_3d": uuid_3d,
        "fp_origin_x": fp_data.get("dataStr", {}).get("head", {}).get("x", 0),
        "fp_origin_y": fp_data.get("dataStr", {}).get("head", {}).get("y", 0),
        "sym_origin_x": primary.get("dataStr", {}).get("head", {}).get("x", 0) if sym_data_list else 0,
        "sym_origin_y": primary.get("dataStr", {}).get("head", {}).get("y", 0) if sym_data_list else 0,
    }
