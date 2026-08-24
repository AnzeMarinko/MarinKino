import unittest

from weather_service import (
    build_weather_data,
    hours_until_next_full_moon,
    summarize_weather_code,
)


class WeatherServiceTests(unittest.TestCase):
    def test_next_full_moon_countdown_returns_positive_hours(self):
        self.assertEqual(hours_until_next_full_moon(0.29), 149)
        self.assertEqual(hours_until_next_full_moon(0.5), 709)
        self.assertEqual(hours_until_next_full_moon(0.29, 18), 131)

    def test_build_weather_data_uses_current_and_daily_values(self):
        payload = {
            "timezone": "Europe/Ljubljana",
            "current": {
                "temperature_2m": 18.5,
                "is_day": 1,
                "precipitation": 0.4,
                "weather_code": 2,
                "wind_speed_10m": 12.5,
                "cloud_cover": 40,
            },
            "daily": {
                "time": ["2026-08-18", "2026-08-19"],
                "weather_code": [2, 61],
                "temperature_2m_max": [21.0, 19.5],
                "temperature_2m_min": [13.5, 14.0],
                "precipitation_sum": [0.0, 3.8],
                "sunrise": ["2026-08-18T05:30", "2026-08-19T05:31"],
                "sunset": ["2026-08-18T20:41", "2026-08-19T20:40"],
                "moon_phase": [0.5, 0.75],
            },
            "minutely_15": {
                "time": ["2026-08-18T00:00", "2026-08-18T00:15"],
                "temperature_2m": [18.5, 18.4],
            },
        }

        weather = build_weather_data(payload, "Ljubljana")

        self.assertEqual(weather["location"], "Ljubljana")
        self.assertEqual(weather["current"]["temperature"], 18.5)
        self.assertEqual(weather["daily"][0]["weather_code"], 2)
        self.assertEqual(weather["daily"][0]["weekday"], "torek")
        self.assertEqual(weather["daily"][0]["moon_label"], "Polna luna")
        self.assertEqual(weather["daily"][0]["moon_illumination"], 100)
        self.assertEqual(weather["daily"][0]["moon_shadow_offset"], 100)
        self.assertEqual(weather["daily"][1]["precipitation_sum"], 3.8)
        self.assertEqual(weather["minutely_15"]["time"][1], "2026-08-18T00:15")

    def test_weather_code_summary_maps_known_code(self):
        self.assertIn("sončno", summarize_weather_code(0).lower())
        self.assertIn("dež", summarize_weather_code(61).lower())

    def test_weather_icon_classes_are_color_coded_for_current_and_forecast(
        self,
    ):
        payload = {
            "timezone": "Europe/Ljubljana",
            "current": {"weather_code": 0},
            "daily": {
                "time": ["2026-08-18", "2026-08-19"],
                "weather_code": [0, 45],
            },
        }

        weather = build_weather_data(payload, "Ljubljana")

        self.assertEqual(weather["current"]["weather_icon_class"], "sunny")
        self.assertEqual(weather["daily"][0]["weather_icon_class"], "sunny")
        self.assertEqual(weather["daily"][1]["weather_icon_class"], "fog")


if __name__ == "__main__":
    unittest.main()
