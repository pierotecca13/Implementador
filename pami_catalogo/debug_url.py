"""Diagnóstico: detecta el formato del archivo descargado desde PAMI."""
import re
import requests

BASE_URL = "https://trazabilidad.pami.org.ar"
PAGE_URL = f"{BASE_URL}/trazamed/consultaCatalogoByGTIN.tz"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

resp = session.get(PAGE_URL, timeout=30)
dt_match = re.search(r"dt:'(z_[a-zA-Z0-9]+)'", resp.text)
desktop_id = dt_match.group(1)
jsessionid = session.cookies.get("JSESSIONID", "")

au_url = f"{BASE_URL}/trazamed/zkau;jsessionid={jsessionid}"
session.post(au_url, timeout=60, data={
    "dtid":   desktop_id,
    "cmd_0":  "onClick",
    "uuid_0": "zk_comp_51",
    "data_0": '{"x":1,"y":1,"which":1,"x0":0,"y0":0,"cntx":1,"cnty":1,"keys":0}',
})

excel_url = f"{BASE_URL}/trazamed/CatalogoGtinExcel;jsessionid={jsessionid}"
file_resp = session.get(excel_url, timeout=120)

content = file_resp.content
print(f"Content-Type header : {file_resp.headers.get('Content-Type')}")
print(f"Content-Disposition : {file_resp.headers.get('Content-Disposition', 'no presente')}")
print(f"Tamaño              : {len(content)} bytes")
print(f"Primeros 8 bytes    : {content[:8].hex()}  →  {content[:8]}")
