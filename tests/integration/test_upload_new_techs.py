"""
E2E / Validation testi: Yeni teknoloji tipleri (WCDMA, GSM, 5G, Unknown)

Sınanan şey
-----------
1. parse_csv()   — CSV string'ini RawMeasurementCreate listesine dönüştürür;
                   yeni teknoloji değerleri Pydantic validation'dan geçmeli.
2. clean_batch() — validate_ranges + deduplicate pipeline'ı; yeni teknolojiler
                   reddedilmemeli.
3. HTTP katmanı  — POST /api/v1/measurements/upload; DB gerektiren testler için
                   gerçek bağlantı varsa çalışır, yoksa skip edilir.

Not: "API Key" authentication mevcut kodda yok; eklenirse buraya
     headers={"X-API-Key": settings.API_KEY} eklenmeli.
"""

from __future__ import annotations

import io
import textwrap

import pytest
import pytest_asyncio
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.models.raw_measurement import Technology
from app.services.cleaning import clean_batch
from app.services.ingestion import parse_csv
from app.schemas.raw_measurement import RawMeasurementCreate


# ── Yardımcı: ham CSV string'inden UploadFile oluştur ─────────────────────────

def _make_upload_file(csv_text: str, filename: str = "test.csv") -> UploadFile:
    content = csv_text.strip().encode()
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers=Headers({"content-type": "text/csv"}),
    )


# ── CSV sabitleri ─────────────────────────────────────────────────────────────

_OPERATOR = "28601"

_CSV_MIXED = textwrap.dedent(f"""
    device_timestamp,lat,lon,accuracy,operator_id,technology,rsrp,sinr
    2026-04-21T10:00:00+00:00,41.010,29.010,15.0,{_OPERATOR},WCDMA,-95.0,3.0
    2026-04-21T10:01:00+00:00,41.020,29.020,20.0,{_OPERATOR},Unknown,,
    2026-04-21T10:02:00+00:00,41.030,29.030,12.0,{_OPERATOR},GSM,-90.0,5.0
""")

_CSV_ALL_TECHS = textwrap.dedent(f"""
    device_timestamp,lat,lon,accuracy,operator_id,technology,rsrp,sinr
    2026-04-21T12:00:00+00:00,41.01,29.01,10.0,{_OPERATOR},LTE,-85.0,12.0
    2026-04-21T12:01:00+00:00,41.02,29.02,10.0,{_OPERATOR},NR,-78.0,18.0
    2026-04-21T12:02:00+00:00,41.03,29.03,15.0,{_OPERATOR},WCDMA,-100.0,2.0
    2026-04-21T12:03:00+00:00,41.04,29.04,20.0,{_OPERATOR},GSM,-92.0,4.0
    2026-04-21T12:04:00+00:00,41.05,29.05,12.0,{_OPERATOR},5G,-80.0,15.0
    2026-04-21T12:05:00+00:00,41.06,29.06,30.0,{_OPERATOR},Unknown,,
""")

_CSV_UNKNOWN_NO_METRICS = textwrap.dedent(f"""
    device_timestamp,lat,lon,accuracy,operator_id,technology,rsrp,sinr
    2026-04-21T11:00:00+00:00,41.050,29.050,25.0,{_OPERATOR},Unknown,,
""")


# ═══════════════════════════════════════════════════════════════════════════════
# Birim Testleri — DB gerektirmez
# ═══════════════════════════════════════════════════════════════════════════════

class TestTechnologyEnumExpansion:
    """Technology enum'un yeni değerleri doğru temsil ettiğini doğrular."""

    def test_all_six_values_exist(self):
        values = {t.value for t in Technology}
        assert "LTE"     in values
        assert "NR"      in values
        assert "5G"      in values
        assert "WCDMA"   in values
        assert "GSM"     in values
        assert "Unknown" in values

    def test_case_sensitivity_unknown(self):
        """'Unknown' büyük/küçük harf tam eşleşmeli."""
        assert Technology("Unknown") is Technology.UNKNOWN
        with pytest.raises(ValueError):
            Technology("unknown")
        with pytest.raises(ValueError):
            Technology("UNKNOWN")

    def test_5g_python_name(self):
        """'5G' değeri FIVEG adıyla Python tarafından erişilebilir."""
        assert Technology.FIVEG.value == "5G"
        assert Technology("5G") is Technology.FIVEG

    def test_pydantic_accepts_new_technologies(self):
        """RawMeasurementCreate yeni teknoloji değerlerini kabul etmeli."""
        base = dict(
            device_timestamp="2026-04-21T10:00:00+00:00",
            lat=41.0, lon=29.0,
            operator_id=_OPERATOR,
        )
        for tech_str in ("WCDMA", "GSM", "5G", "Unknown"):
            row = RawMeasurementCreate(**base, technology=tech_str)
            assert row.technology.value == tech_str, f"Failed for {tech_str}"

    def test_pydantic_rejects_invalid_technology(self):
        """Bilinmeyen bir teknoloji değeri hâlâ reddedilmeli."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            RawMeasurementCreate(
                device_timestamp="2026-04-21T10:00:00+00:00",
                lat=41.0, lon=29.0,
                operator_id=_OPERATOR,
                technology="CDMA2000",  # hiç tanımlanmamış
            )


class TestParseCsvNewTechs:
    """parse_csv'nin yeni teknoloji değerlerini hata vermeden işlediğini doğrular."""

    @pytest.mark.asyncio
    async def test_wcdma_gsm_unknown_parsed_without_errors(self):
        upload = _make_upload_file(_CSV_MIXED)
        rows, errors = await parse_csv(upload)

        tech_errors = [e for e in errors if "technology" in e.lower()
                       or "input should be" in e.lower()]
        assert tech_errors == [], f"Teknoloji doğrulama hatası: {tech_errors}"
        assert len(rows) == 3, f"3 satır beklendi, {len(rows)} geldi. Hatalar: {errors}"

    @pytest.mark.asyncio
    async def test_all_six_technologies_parsed(self):
        upload = _make_upload_file(_CSV_ALL_TECHS)
        rows, errors = await parse_csv(upload)

        tech_errors = [e for e in errors if "technology" in e.lower()
                       or "input should be" in e.lower()]
        assert tech_errors == [], f"Teknoloji doğrulama hatası: {tech_errors}"
        assert len(rows) == 6, f"6 satır beklendi, {len(rows)} geldi. Hatalar: {errors}"

        parsed_techs = {r.technology.value for r in rows}
        assert parsed_techs == {"LTE", "NR", "WCDMA", "GSM", "5G", "Unknown"}

    @pytest.mark.asyncio
    async def test_unknown_with_null_metrics_parsed(self):
        """Unknown teknoloji + boş sinyal metrikleri kabul edilmeli."""
        upload = _make_upload_file(_CSV_UNKNOWN_NO_METRICS)
        rows, errors = await parse_csv(upload)

        tech_errors = [e for e in errors if "technology" in e.lower()
                       or "input should be" in e.lower()]
        assert tech_errors == [], f"Teknoloji doğrulama hatası: {tech_errors}"
        assert len(rows) == 1
        assert rows[0].technology is Technology.UNKNOWN
        assert rows[0].rsrp is None
        assert rows[0].sinr is None


class TestCleanBatchNewTechs:
    """clean_batch pipeline'ının yeni teknolojileri reddetmediğini doğrular."""

    @pytest.mark.asyncio
    async def test_wcdma_gsm_unknown_survive_cleaning(self):
        upload = _make_upload_file(_CSV_MIXED)
        rows, _ = await parse_csv(upload)
        cleaned, errors = clean_batch(rows)

        tech_errors = [e for e in errors if "technology" in e.lower()]
        assert tech_errors == [], f"Cleaning teknoloji hatası: {tech_errors}"
        # En az 1 satır temizlenmeli (Unknown'un metrikleri yok ama
        # validation reddinde teknoloji nedeni olmamalı)
        assert len(cleaned) >= 1, f"Hiç satır temizlenmedi. Hatalar: {errors}"

    @pytest.mark.asyncio
    async def test_unknown_null_metrics_survives_cleaning(self):
        """Unknown + null metrikler cleaning pipeline'ından geçmeli."""
        upload = _make_upload_file(_CSV_UNKNOWN_NO_METRICS)
        rows, _ = await parse_csv(upload)
        cleaned, errors = clean_batch(rows)

        tech_errors = [e for e in errors if "technology" in e.lower()]
        assert tech_errors == [], f"Teknoloji kaynaklı hata: {tech_errors}"
        # Unknown + null metrik: cleaning reddedebilir (rsrp yoksa range geçmez)
        # ama hata mesajı "technology" içermemeli
        assert all("technology" not in e.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_all_techs_no_technology_rejection(self):
        """Tüm 6 teknoloji tipi — cleaning hiçbirini teknoloji nedeniyle reddetmemeli."""
        upload = _make_upload_file(_CSV_ALL_TECHS)
        rows, _ = await parse_csv(upload)
        _, errors = clean_batch(rows)

        tech_errors = [e for e in errors if "technology" in e.lower()]
        assert tech_errors == [], f"Beklenmeyen teknoloji reddi: {tech_errors}"


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP Entegrasyon Testleri — Gerçek DB gerekir
# ═══════════════════════════════════════════════════════════════════════════════

def _csv_multipart(content: str) -> list:
    return [("file", ("measurements.csv", io.BytesIO(content.strip().encode()), "text/csv"))]


@pytest.mark.asyncio
async def test_upload_new_technology_types_http(client):
    """
    HTTP 202 — WCDMA, Unknown, GSM içeren CSV'yi yükle; accepted > 0 olmalı.
    Bu test gerçek DB bağlantısı gerektirir (docker compose up -d db).
    """
    resp = await client.post(
        "/api/v1/measurements/upload",
        files=_csv_multipart(_CSV_MIXED),
    )
    assert resp.status_code == 202, f"Beklenen 202, gelen {resp.status_code}. Body: {resp.text}"

    body = resp.json()
    assert body["accepted"] > 0, f"accepted > 0 beklendi: {body}"

    tech_errors = [e for e in body.get("errors", [])
                   if "technology" in e.lower() or "input should be" in e.lower()]
    assert tech_errors == [], f"Teknoloji validation hatası: {tech_errors}"


@pytest.mark.asyncio
async def test_upload_all_six_technologies_http(client):
    """
    Tüm 6 teknoloji tipi (LTE, NR, 5G, WCDMA, GSM, Unknown) içeren CSV yüklenir.
    Hiçbiri teknoloji nedeniyle reddedilmemeli.
    """
    resp = await client.post(
        "/api/v1/measurements/upload",
        files=_csv_multipart(_CSV_ALL_TECHS),
    )
    assert resp.status_code == 202, resp.text

    body = resp.json()
    tech_errors = [e for e in body.get("errors", [])
                   if "technology" in e.lower() or "input should be" in e.lower()]
    assert tech_errors == [], f"Teknoloji validation hatası: {tech_errors}"
    assert body["accepted"] > 0, f"En az 1 satır beklendi: {body}"
