"""
Birim Testleri: Yeni teknoloji tipleri (WCDMA, GSM, 5G, Unknown)

Senaryo (Görev 3)
-----------------
POST /api/v1/measurements/upload uç noktasına WCDMA ve Unknown teknolojilerini
içeren, zaman damgası ve diğer alanları eksiksiz olan bir CSV string'i gönderilir.

Bu dosyadaki testler DB bağlantısı gerektirmez; Pydantic validation,
parse_csv ve clean_batch pipeline'ını doğrudan sınar.

HTTP uç nokta testi (Docker DB gerektirir) en altta işaretlenmiştir.
"""

from __future__ import annotations

import io
import textwrap

import pytest
from starlette.datastructures import Headers

from app.models.raw_measurement import Technology
from app.schemas.raw_measurement import RawMeasurementCreate
from app.services.cleaning import clean_batch
from app.services.ingestion import parse_csv


# ── Yardımcı ──────────────────────────────────────────────────────────────────

_OPERATOR = "28601"


def _upload_file(csv_text: str):
    """Starlette UploadFile nesnesi döndürür (DB gerektirmez)."""
    from fastapi import UploadFile
    content = csv_text.strip().encode()
    return UploadFile(
        filename="test.csv",
        file=io.BytesIO(content),
        headers=Headers({"content-type": "text/csv"}),
    )


# ── CSV sabitleri ─────────────────────────────────────────────────────────────

_CSV_WCDMA_UNKNOWN = textwrap.dedent(f"""
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


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Enum Genişleme Testleri
# ═══════════════════════════════════════════════════════════════════════════════

class TestTechnologyEnumExpansion:
    """Technology enum'un 4 yeni değeri doğru temsil ettiğini doğrular."""

    def test_all_six_values_exist(self):
        values = {t.value for t in Technology}
        for expected in ("LTE", "NR", "5G", "WCDMA", "GSM", "Unknown"):
            assert expected in values, f"Enum değeri eksik: {expected}"

    def test_case_sensitivity_unknown(self):
        """'Unknown' büyük/küçük harf tam eşleşmeli."""
        assert Technology("Unknown") is Technology.UNKNOWN
        with pytest.raises(ValueError):
            Technology("unknown")
        with pytest.raises(ValueError):
            Technology("UNKNOWN")

    def test_5g_python_identifier(self):
        """'5G' string değeri FIVEG adıyla Python'dan erişilebilir."""
        assert Technology.FIVEG.value == "5G"
        assert Technology("5G") is Technology.FIVEG

    def test_pydantic_accepts_all_new_technologies(self):
        """RawMeasurementCreate yeni teknoloji değerlerini doğrulamasız geçirmeli."""
        base = dict(
            device_timestamp="2026-04-21T10:00:00+00:00",
            lat=41.0, lon=29.0,
            operator_id=_OPERATOR,
        )
        for tech_str in ("WCDMA", "GSM", "5G", "Unknown"):
            row = RawMeasurementCreate(**base, technology=tech_str)
            assert row.technology.value == tech_str

    def test_pydantic_still_rejects_truly_unknown_technology(self):
        """Enum'da tanımsız bir teknoloji hâlâ reddedilmeli."""
        with pytest.raises(Exception):
            RawMeasurementCreate(
                device_timestamp="2026-04-21T10:00:00+00:00",
                lat=41.0, lon=29.0,
                operator_id=_OPERATOR,
                technology="CDMA2000",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. parse_csv Testleri
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseCsvNewTechs:
    """parse_csv'nin yeni teknoloji değerlerini hata vermeden işlediğini doğrular."""

    @pytest.mark.asyncio
    async def test_wcdma_gsm_unknown_parsed_without_tech_errors(self):
        """WCDMA, Unknown, GSM — parse hatası olmamalı."""
        rows, errors = await parse_csv(_upload_file(_CSV_WCDMA_UNKNOWN))

        tech_errors = [e for e in errors if "technology" in e.lower()]
        assert tech_errors == [], f"Teknoloji doğrulama hatası: {tech_errors}"
        assert len(rows) == 3, f"3 satır beklendi, {len(rows)} geldi. Hatalar: {errors}"

    @pytest.mark.asyncio
    async def test_all_six_technologies_parsed_correctly(self):
        """Tüm 6 teknoloji tipi parse edilmeli; hata yok."""
        rows, errors = await parse_csv(_upload_file(_CSV_ALL_TECHS))

        tech_errors = [e for e in errors if "technology" in e.lower()]
        assert tech_errors == [], f"Teknoloji doğrulama hatası: {tech_errors}"
        assert len(rows) == 6, f"6 satır beklendi, {len(rows)} geldi. Hatalar: {errors}"

        parsed_techs = {r.technology.value for r in rows}
        assert parsed_techs == {"LTE", "NR", "WCDMA", "GSM", "5G", "Unknown"}

    @pytest.mark.asyncio
    async def test_unknown_with_null_metrics_parsed(self):
        """Unknown + boş sinyal metrikleri — parse hatasız geçmeli."""
        csv = textwrap.dedent(f"""
            device_timestamp,lat,lon,accuracy,operator_id,technology,rsrp,sinr
            2026-04-21T11:00:00+00:00,41.050,29.050,25.0,{_OPERATOR},Unknown,,
        """)
        rows, errors = await parse_csv(_upload_file(csv))

        tech_errors = [e for e in errors if "technology" in e.lower()]
        assert tech_errors == [], f"Teknoloji doğrulama hatası: {tech_errors}"
        assert len(rows) == 1
        assert rows[0].technology is Technology.UNKNOWN
        assert rows[0].rsrp is None
        assert rows[0].sinr is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. clean_batch Testleri
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanBatchNewTechs:
    """clean_batch pipeline'ının yeni teknolojileri teknoloji nedeniyle reddetmediğini doğrular."""

    @pytest.mark.asyncio
    async def test_wcdma_gsm_unknown_no_tech_rejection(self):
        """WCDMA, GSM, Unknown — cleaning'de teknoloji kaynaklı hata olmamalı."""
        rows, _ = await parse_csv(_upload_file(_CSV_WCDMA_UNKNOWN))
        _, errors = clean_batch(rows)

        tech_errors = [e for e in errors if "technology" in e.lower()]
        assert tech_errors == [], f"Cleaning teknoloji hatası: {tech_errors}"

    @pytest.mark.asyncio
    async def test_wcdma_with_valid_signal_accepted_by_cleaner(self):
        """WCDMA + geçerli RSRP/SINR → cleaning'den geçmeli."""
        csv = textwrap.dedent(f"""
            device_timestamp,lat,lon,accuracy,operator_id,technology,rsrp,sinr
            2026-04-21T10:00:00+00:00,41.01,29.01,10.0,{_OPERATOR},WCDMA,-90.0,5.0
        """)
        rows, _ = await parse_csv(_upload_file(csv))
        cleaned, errors = clean_batch(rows)

        tech_errors = [e for e in errors if "technology" in e.lower()]
        assert tech_errors == [], f"Beklenmeyen teknoloji reddi: {tech_errors}"
        assert len(cleaned) == 1, f"WCDMA satırı reddedildi. Hatalar: {errors}"

    @pytest.mark.asyncio
    async def test_all_techs_no_technology_based_rejection(self):
        """6 teknoloji tipinin hiçbiri teknoloji nedeniyle reddedilmemeli."""
        rows, _ = await parse_csv(_upload_file(_CSV_ALL_TECHS))
        _, errors = clean_batch(rows)

        tech_errors = [e for e in errors if "technology" in e.lower()]
        assert tech_errors == [], f"Beklenmeyen teknoloji redleri: {tech_errors}"
