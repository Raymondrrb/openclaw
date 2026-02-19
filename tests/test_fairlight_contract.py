#!/usr/bin/env python3
"""Tests for rayvault/fairlight_contract.py — Fairlight bus contract."""

from __future__ import annotations

import unittest

from rayvault.fairlight_contract import (
    BusDef,
    ContractVerifyResult,
    DuckingDef,
    FairlightContract,
    apply_bus_contract_stubs,
    verify_bus_contract,
)
from rayvault.policies import (
    BUS_MASTER_NAME,
    BUS_MUSIC_NAME,
    BUS_SFX_NAME,
    BUS_VO_NAME,
    SOUNDTRACK_CROSSFADE_IN_SEC,
    SOUNDTRACK_CROSSFADE_OUT_SEC,
    SOUNDTRACK_DUCK_AMOUNT_DB,
    SOUNDTRACK_DUCK_ATTACK_MS,
    SOUNDTRACK_DUCK_RELEASE_MS,
)


# ---------------------------------------------------------------
# BusDef
# ---------------------------------------------------------------

class TestBusDef(unittest.TestCase):

    def test_basic_creation(self):
        b = BusDef(name="BUS_VO", track_type="audio", track_index=1)
        self.assertEqual(b.name, "BUS_VO")
        self.assertEqual(b.track_type, "audio")
        self.assertEqual(b.track_index, 1)
        self.assertEqual(b.source_description, "")

    def test_source_description(self):
        b = BusDef(name="BUS_VO", track_type="audio", track_index=1,
                   source_description="02_audio.wav")
        self.assertEqual(b.source_description, "02_audio.wav")


# ---------------------------------------------------------------
# DuckingDef
# ---------------------------------------------------------------

class TestDuckingDef(unittest.TestCase):

    def test_basic_creation(self):
        d = DuckingDef(
            target_bus="BUS_MUSIC",
            key_input_bus="BUS_VO",
            reduction_db=12,
            attack_ms=20,
            release_ms=250,
        )
        self.assertEqual(d.target_bus, "BUS_MUSIC")
        self.assertEqual(d.key_input_bus, "BUS_VO")
        self.assertEqual(d.reduction_db, 12)
        self.assertEqual(d.attack_ms, 20)
        self.assertEqual(d.release_ms, 250)


# ---------------------------------------------------------------
# FairlightContract.default()
# ---------------------------------------------------------------

class TestFairlightContractDefault(unittest.TestCase):

    def setUp(self):
        self.contract = FairlightContract.default()

    def test_has_three_buses(self):
        self.assertEqual(len(self.contract.buses), 3)

    def test_bus_names(self):
        names = [b.name for b in self.contract.buses]
        self.assertEqual(names, [BUS_VO_NAME, BUS_MUSIC_NAME, BUS_SFX_NAME])

    def test_bus_track_indices(self):
        indices = [b.track_index for b in self.contract.buses]
        self.assertEqual(indices, [1, 2, 3])

    def test_all_buses_audio_type(self):
        for b in self.contract.buses:
            self.assertEqual(b.track_type, "audio")

    def test_vo_bus_description(self):
        vo = self.contract.buses[0]
        self.assertIn("TTS", vo.source_description)

    def test_music_bus_description(self):
        music = self.contract.buses[1]
        self.assertIn("Soundtrack", music.source_description)

    def test_sfx_bus_description(self):
        sfx = self.contract.buses[2]
        self.assertIn("SFX", sfx.source_description)

    def test_ducking_present(self):
        self.assertIsNotNone(self.contract.ducking)

    def test_ducking_target(self):
        self.assertEqual(self.contract.ducking.target_bus, BUS_MUSIC_NAME)

    def test_ducking_key_input(self):
        self.assertEqual(self.contract.ducking.key_input_bus, BUS_VO_NAME)

    def test_ducking_reduction_from_policy(self):
        self.assertEqual(self.contract.ducking.reduction_db, SOUNDTRACK_DUCK_AMOUNT_DB)

    def test_ducking_attack_from_policy(self):
        self.assertEqual(self.contract.ducking.attack_ms, SOUNDTRACK_DUCK_ATTACK_MS)

    def test_ducking_release_from_policy(self):
        self.assertEqual(self.contract.ducking.release_ms, SOUNDTRACK_DUCK_RELEASE_MS)

    def test_fades_present(self):
        self.assertIn("music_fade_in_sec", self.contract.fades)
        self.assertIn("music_fade_out_sec", self.contract.fades)

    def test_fade_in_from_policy(self):
        self.assertEqual(self.contract.fades["music_fade_in_sec"], SOUNDTRACK_CROSSFADE_IN_SEC)

    def test_fade_out_from_policy(self):
        self.assertEqual(self.contract.fades["music_fade_out_sec"], SOUNDTRACK_CROSSFADE_OUT_SEC)

    def test_master_bus(self):
        self.assertEqual(self.contract.master_bus, BUS_MASTER_NAME)


# ---------------------------------------------------------------
# FairlightContract.to_dict()
# ---------------------------------------------------------------

class TestFairlightContractToDict(unittest.TestCase):

    def setUp(self):
        self.d = FairlightContract.default().to_dict()

    def test_top_level_keys(self):
        for key in ("buses", "ducking", "fades", "master_bus"):
            self.assertIn(key, self.d)

    def test_buses_list_of_dicts(self):
        self.assertIsInstance(self.d["buses"], list)
        for b in self.d["buses"]:
            self.assertIsInstance(b, dict)
            for k in ("name", "track_type", "track_index", "source_description"):
                self.assertIn(k, b)

    def test_ducking_dict(self):
        duck = self.d["ducking"]
        self.assertIsInstance(duck, dict)
        for k in ("target_bus", "key_input_bus", "reduction_db", "attack_ms", "release_ms"):
            self.assertIn(k, duck)

    def test_fades_dict(self):
        self.assertIsInstance(self.d["fades"], dict)

    def test_master_bus_str(self):
        self.assertIsInstance(self.d["master_bus"], str)

    def test_no_ducking_returns_none(self):
        c = FairlightContract(buses=[], ducking=None)
        d = c.to_dict()
        self.assertIsNone(d["ducking"])


# ---------------------------------------------------------------
# ContractVerifyResult
# ---------------------------------------------------------------

class TestContractVerifyResult(unittest.TestCase):

    def test_defaults(self):
        r = ContractVerifyResult()
        self.assertTrue(r.ok)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, [])
        self.assertEqual(r.applied_via, "")

    def test_to_dict(self):
        r = ContractVerifyResult(ok=False, errors=["E1"], warnings=["W1"], applied_via="api")
        d = r.to_dict()
        self.assertFalse(d["ok"])
        self.assertEqual(d["errors"], ["E1"])
        self.assertEqual(d["warnings"], ["W1"])
        self.assertEqual(d["applied_via"], "api")

    def test_to_dict_keys(self):
        d = ContractVerifyResult().to_dict()
        self.assertEqual(set(d.keys()), {"ok", "errors", "warnings", "applied_via"})


# ---------------------------------------------------------------
# verify_bus_contract
# ---------------------------------------------------------------

class TestVerifyBusContract(unittest.TestCase):

    def setUp(self):
        self.contract = FairlightContract.default()

    def test_no_soundtrack_receipt(self):
        result = verify_bus_contract(self.contract, {})
        self.assertTrue(result.ok)
        self.assertEqual(result.applied_via, "none")
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("soundtrack_receipt", result.warnings[0])

    def test_empty_soundtrack_receipt(self):
        result = verify_bus_contract(self.contract, {"soundtrack_receipt": {}})
        self.assertTrue(result.ok)
        self.assertEqual(result.applied_via, "none")

    def test_full_pass(self):
        receipt = {
            "soundtrack_receipt": {
                "applied_in_davinci": True,
                "fades_applied": True,
                "ducking_applied": True,
            }
        }
        result = verify_bus_contract(self.contract, receipt)
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.applied_via, "api")

    def test_music_not_applied_error(self):
        receipt = {
            "soundtrack_receipt": {
                "applied_in_davinci": False,
                "fades_applied": True,
                "ducking_applied": True,
            }
        }
        result = verify_bus_contract(self.contract, receipt)
        self.assertFalse(result.ok)
        self.assertTrue(any("BUS_MUSIC" in e for e in result.errors))
        self.assertEqual(result.applied_via, "none")

    def test_no_fades_warning(self):
        receipt = {
            "soundtrack_receipt": {
                "applied_in_davinci": True,
                "fades_applied": False,
                "ducking_applied": True,
            }
        }
        result = verify_bus_contract(self.contract, receipt)
        self.assertTrue(result.ok)
        self.assertTrue(any("fades" in w for w in result.warnings))

    def test_no_ducking_warning(self):
        receipt = {
            "soundtrack_receipt": {
                "applied_in_davinci": True,
                "fades_applied": True,
                "ducking_applied": False,
            }
        }
        result = verify_bus_contract(self.contract, receipt)
        self.assertTrue(result.ok)
        self.assertTrue(any("DUCKING" in w for w in result.warnings))

    def test_all_issues_combined(self):
        receipt = {
            "soundtrack_receipt": {
                "applied_in_davinci": False,
                "fades_applied": False,
                "ducking_applied": False,
            }
        }
        result = verify_bus_contract(self.contract, receipt)
        self.assertFalse(result.ok)
        self.assertGreater(len(result.errors), 0)
        self.assertGreater(len(result.warnings), 0)

    def test_partial_receipt_missing_keys(self):
        """Missing keys are treated as falsy."""
        receipt = {"soundtrack_receipt": {"applied_in_davinci": True}}
        result = verify_bus_contract(self.contract, receipt)
        self.assertTrue(result.ok)  # Music applied, so no error
        # Fades + ducking warnings
        self.assertGreaterEqual(len(result.warnings), 2)


# ---------------------------------------------------------------
# apply_bus_contract_stubs
# ---------------------------------------------------------------

class TestApplyBusContractStubs(unittest.TestCase):

    def test_returns_evidence_dict(self):
        contract = FairlightContract.default()
        ev = apply_bus_contract_stubs(None, contract)
        self.assertIsInstance(ev, dict)

    def test_evidence_keys(self):
        ev = apply_bus_contract_stubs(None, FairlightContract.default())
        for key in ("attempted", "api_available", "buses_created", "ducking_configured", "notes"):
            self.assertIn(key, ev)

    def test_stub_not_available(self):
        ev = apply_bus_contract_stubs(None, FairlightContract.default())
        self.assertTrue(ev["attempted"])
        self.assertFalse(ev["api_available"])
        self.assertFalse(ev["ducking_configured"])
        self.assertEqual(ev["buses_created"], [])


if __name__ == "__main__":
    unittest.main()
