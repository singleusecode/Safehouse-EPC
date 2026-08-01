import json
from datetime import datetime, timezone
import truststore

truststore.inject_into_ssl()
import pandas as pd
import requests
import streamlit as st
import urllib3


st.set_page_config(
    page_title="WiseWatt API Test",
    page_icon="⚡",
    layout="wide",
)

DEFAULT_BASE_URL = "https://api.wisewatt.uk.cgi.com/api/v1"
INVENTORY_ENDPOINT = "/inventory/manual"


def get_secret(name: str, default: str = "") -> str:
    """Read a Streamlit secret without crashing the page."""
    try:
        value = st.secrets.get(name, default)
        return str(value).strip() if value is not None else default
    except Exception:
        return default


def normalise_base_url(url: str) -> str:
    return url.strip().rstrip("/")


def normalise_postcode(postcode: str) -> str:
    return " ".join(postcode.upper().split())


def auth_value(api_key: str) -> str:
    """
    WiseWatt documentation shows the header value as 'Bearer <key>'.
    Avoid adding Bearer twice if it is already present in secrets.toml.
    """
    key = api_key.strip()
    if key.lower().startswith("bearer "):
        return key
    return f"Bearer {key}"


def mask_key(api_key: str) -> str:
    clean = api_key.replace("Bearer ", "").replace("bearer ", "").strip()
    if len(clean) <= 8:
        return "••••••••" if clean else "Not configured"
    return f"{clean[:4]}••••••••{clean[-4:]}"


def parse_response(response: requests.Response):
    try:
        return response.json()
    except ValueError:
        return response.text


def inventory_request(
    base_url: str,
    api_key: str,
    postcode: str,
    address_identifier: str,
    meter_type: str,
    timeout_seconds: int,
    verify_ssl: bool,
) -> dict:
    url = f"{normalise_base_url(base_url)}{INVENTORY_ENDPOINT}"

    payload = {
        "postCode": normalise_postcode(postcode),
        "addressIdentifier": address_identifier.strip(),
        "meterType": meter_type,
    }

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "wisewatt-api-key-token": auth_value(api_key),
    }

    verify_setting = True if verify_ssl else False

    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    started = datetime.now(timezone.utc)

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout_seconds,
            verify=verify_setting,
        )

        elapsed_ms = round(response.elapsed.total_seconds() * 1000, 1)
        response_data = parse_response(response)

        return {
            "ok": response.ok,
            "requested_at": started.isoformat(),
            "url": url,
            "method": "POST",
            "meter_type": meter_type,
            "payload": payload,
            "status_code": response.status_code,
            "reason": response.reason,
            "elapsed_ms": elapsed_ms,
            "content_type": response.headers.get("content-type", ""),
            "response": response_data,
            "error_type": None,
            "error": None,
        }

    except requests.exceptions.SSLError as exc:
        return {
            "ok": False,
            "requested_at": started.isoformat(),
            "url": url,
            "method": "POST",
            "meter_type": meter_type,
            "payload": payload,
            "status_code": None,
            "reason": None,
            "elapsed_ms": None,
            "content_type": None,
            "response": None,
            "error_type": "SSL certificate error",
            "error": str(exc),
        }

    except requests.exceptions.Timeout as exc:
        return {
            "ok": False,
            "requested_at": started.isoformat(),
            "url": url,
            "method": "POST",
            "meter_type": meter_type,
            "payload": payload,
            "status_code": None,
            "reason": None,
            "elapsed_ms": None,
            "content_type": None,
            "response": None,
            "error_type": "Request timed out",
            "error": str(exc),
        }

    except requests.exceptions.ConnectionError as exc:
        return {
            "ok": False,
            "requested_at": started.isoformat(),
            "url": url,
            "method": "POST",
            "meter_type": meter_type,
            "payload": payload,
            "status_code": None,
            "reason": None,
            "elapsed_ms": None,
            "content_type": None,
            "response": None,
            "error_type": "Connection error",
            "error": str(exc),
        }

    except requests.exceptions.RequestException as exc:
        return {
            "ok": False,
            "requested_at": started.isoformat(),
            "url": url,
            "method": "POST",
            "meter_type": meter_type,
            "payload": payload,
            "status_code": None,
            "reason": None,
            "elapsed_ms": None,
            "content_type": None,
            "response": None,
            "error_type": "HTTP request error",
            "error": str(exc),
        }


def render_result(result: dict) -> None:
    meter_name = str(result["meter_type"]).title()

    if result["ok"]:
        st.success(
            f"{meter_name}: request succeeded "
            f"(HTTP {result['status_code']}, {result['elapsed_ms']} ms)"
        )
    elif result["status_code"] is not None:
        st.error(
            f"{meter_name}: API returned HTTP "
            f"{result['status_code']} {result['reason'] or ''}".strip()
        )
    else:
        st.error(f"{meter_name}: {result['error_type']}")

    tab_response, tab_request, tab_diagnostics = st.tabs(
        ["Response", "Request", "Diagnostics"]
    )

    with tab_response:
        response_data = result.get("response")
        if isinstance(response_data, (dict, list)):
            st.json(response_data)
        elif response_data:
            st.code(str(response_data), language="text")
        else:
            st.info("No response body was returned.")

    with tab_request:
        st.code(
            json.dumps(result["payload"], indent=2),
            language="json",
        )
        st.caption(f"POST {result['url']}")

    with tab_diagnostics:
        diagnostics = {
            "Requested at (UTC)": result["requested_at"],
            "Status code": result["status_code"],
            "Reason": result["reason"],
            "Elapsed (ms)": result["elapsed_ms"],
            "Content-Type": result["content_type"],
            "Error type": result["error_type"],
            "Error": result["error"],
        }
        st.json(diagnostics)


st.title("⚡ WiseWatt Production API Test")
st.caption(
    "Streamlit page for testing the WiseWatt inventory API."
)

api_key = get_secret("WISEWATT_API_KEY")
secret_base_url = get_secret("WISEWATT_API_URL", DEFAULT_BASE_URL)

with st.sidebar:
    st.header("Configuration")

    base_url = st.text_input(
        "Base URL",
        value=secret_base_url,
        help="Defaults to the WiseWatt production API.",
    )

    st.text_input(
        "API key loaded",
        value=mask_key(api_key),
        disabled=True,
    )

    verify_ssl = st.checkbox(
        "Verify SSL certificate",
        value=True,
        help=(
            "Keep enabled normally. Disable only temporarily to diagnose a "
            "certificate-chain problem."
        ),
    )

    timeout_seconds = st.number_input(
        "Timeout (seconds)",
        min_value=5,
        max_value=120,
        value=30,
        step=5,
    )

    st.divider()
    st.write("**Endpoint**")
    st.code(f"{normalise_base_url(base_url)}{INVENTORY_ENDPOINT}")

    if verify_ssl:
        st.caption("Certificate source: Windows system certificate store")
    else:
        st.warning("SSL verification is disabled for testing.")

if not api_key:
    st.error(
        "WISEWATT_API_KEY is missing. Add it to "
        "`.streamlit/secrets.toml` locally or to Streamlit Cloud Secrets."
    )
    st.code(
        'WISEWATT_API_KEY = "your-production-api-key"\n'
        'WISEWATT_API_URL = "https://api.wisewatt.uk.cgi.com/api/v1"',
        language="toml",
    )
    st.stop()

with st.form("wisewatt_inventory_form"):
    st.subheader("Property lookup")

    col1, col2 = st.columns([1, 2])

    with col1:
        postcode = st.text_input(
            "Postcode",
            placeholder="CF48 3HF",
        )

        lookup_choice = st.radio(
            "Meter lookup",
            options=["Electricity and gas", "Electricity only", "Gas only"],
            horizontal=False,
        )

    with col2:
        address_identifier = st.text_input(
            "Address identifier",
            placeholder="29 Calluna Close",
            help=(
                "The WiseWatt specification requires an addressIdentifier, "
                "postcode and meterType."
            ),
        )

        st.info(
            "Use the address exactly as it is likely to appear in the DCC "
            "inventory. Start with the house number and street."
        )

    submitted = st.form_submit_button(
        "Run inventory test",
        type="primary",
        use_container_width=True,
    )

if submitted:
    if not postcode.strip() or not address_identifier.strip():
        st.warning("Enter both the postcode and address identifier.")
    else:
        meter_types = {
            "Electricity and gas": ["electricity", "gas"],
            "Electricity only": ["electricity"],
            "Gas only": ["gas"],
        }[lookup_choice]

        results = []

        with st.spinner("Calling the WiseWatt production API..."):
            for meter_type in meter_types:
                results.append(
                    inventory_request(
                        base_url=base_url,
                        api_key=api_key,
                        postcode=postcode,
                        address_identifier=address_identifier,
                        meter_type=meter_type,
                        timeout_seconds=int(timeout_seconds),
                        verify_ssl=verify_ssl,
                    )
                )

        st.session_state["wisewatt_test_results"] = results

results = st.session_state.get("wisewatt_test_results", [])

if results:
    st.divider()
    st.subheader("Latest test results")

    for result in results:
        with st.container(border=True):
            render_result(result)

    export_rows = []
    for result in results:
        export_rows.append(
            {
                "requested_at_utc": result["requested_at"],
                "meter_type": result["meter_type"],
                "url": result["url"],
                "postcode": result["payload"]["postCode"],
                "address_identifier": result["payload"]["addressIdentifier"],
                "status_code": result["status_code"],
                "reason": result["reason"],
                "elapsed_ms": result["elapsed_ms"],
                "ok": result["ok"],
                "error_type": result["error_type"],
                "error": result["error"],
                "response": json.dumps(result["response"], default=str),
            }
        )

    export_df = pd.DataFrame(export_rows)

    st.download_button(
        "Download diagnostic CSV",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name=(
            f"wisewatt_api_test_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        ),
        mime="text/csv",
    )

with st.expander("How this page connects"):
    st.markdown(
        """
1. Reads `WISEWATT_API_KEY` from Streamlit secrets.
2. Sends `POST /inventory/manual`.
3. Uses the `wisewatt-api-key-token` HTTP header.
4. Sends `postCode`, `addressIdentifier`, and `meterType`.
5. Shows the raw response and connection diagnostics without exposing the key.
        """
    )
