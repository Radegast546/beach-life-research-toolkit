#!/usr/bin/env python3
"""Focused tests for the building catalog extractor."""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import extract_buildings


BUILDING_LIST_FIXTURE = r'''
    "BUILD_HOTEL"
    "HOTEL_NAME" "Main Hotel"
    "HOTEL_SPRITE" "hotel"
    "HOTEL_COST2BUILD" "15000"
    "HOTEL_REFUNDVALUE" "11250"
    "HOTEL_GRIDWIDTH" "18"
    "HOTEL_GRIDHEIGHT" "12"
    "HOTEL_GUESTCAPACITY" "100"
    {opening_hours_property}
    "HOTEL_POWER" "1000"
    "HOTEL_CATEGORY" "HOTEL"
    "HOTEL_BUILDON" "LAND"
    "HOTEL_MENU" "HotelInfo"
    "HOTEL_CONSTRUCT" "hotel_construct"
    "HOTEL_BUILDTIME" "12"
    "HOTEL_BASEPLATETYPE" "1"
    "HOTEL_NUM_BASEPLATES" "1"
'''

SOURCE_OPENING_HOURS = ("ALLHOURS", "MORNING", "DAY", "EVENING", "NIGHT")


class ExtractBuildingsTests(unittest.TestCase):
    def parse_fixture(self, root, opening_hours_property):
        input_path = root / "BuildingList.txt"
        input_path.write_text(
            BUILDING_LIST_FIXTURE.format(
                opening_hours_property=opening_hours_property
            ),
            encoding="utf-8",
        )
        return extract_buildings.parse_building_list(input_path)

    def test_all_source_opening_hours_are_parsed_and_written_as_ron_identifiers(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output_path = root / "buildings.ron"

            for opening_hours in SOURCE_OPENING_HOURS:
                with self.subTest(opening_hours=opening_hours):
                    buildings = self.parse_fixture(
                        root,
                        f'"HOTEL_OPENINGHOURS" "{opening_hours}"',
                    )
                    self.assertEqual(
                        buildings["hotel"]["opening_hours"], opening_hours
                    )

                    with patch.object(extract_buildings, "ACTIVE_BUILDINGS", ["hotel"]):
                        extract_buildings.write_ron(buildings, output_path)

                    rendered = output_path.read_text(encoding="utf-8")
                    self.assertIn(
                        f"        opening_hours: {opening_hours},\n", rendered
                    )
                    self.assertNotIn(
                        f'opening_hours: "{opening_hours}"', rendered
                    )

    def test_builder_yard_preserves_original_power_demand(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture = BUILDING_LIST_FIXTURE.replace("HOTEL", "BUILDERYARD").format(
                opening_hours_property='"BUILDERYARD_OPENINGHOURS" "ALLHOURS"'
            )
            input_path = root / "BuildingList.txt"
            input_path.write_text(fixture, encoding="utf-8")

            buildings = extract_buildings.parse_building_list(input_path)

            self.assertEqual(buildings["builderyard"]["power"], 1000)

    def test_missing_opening_hours_fails_loudly(self):
        with TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "hotel is missing OPENINGHOURS"):
                self.parse_fixture(Path(temporary_directory), "")

    def test_unknown_opening_hours_fails_loudly(self):
        with TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(
                ValueError, "hotel has unknown OPENINGHOURS 'LUNCH'"
            ):
                self.parse_fixture(
                    Path(temporary_directory),
                    '"HOTEL_OPENINGHOURS" "LUNCH"',
                )


if __name__ == "__main__":
    unittest.main()
