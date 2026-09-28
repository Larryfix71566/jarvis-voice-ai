from __future__ import annotations

import unittest

from scripts.check_process_memory_soak import MIB, summarize, theil_sen_slope


def samples(values: list[int]) -> list[dict[str, float]]:
    return [
        {"elapsed_seconds": float(index), "rss_bytes": value * MIB}
        for index, value in enumerate(values)
    ]


class ProcessMemorySoakTests(unittest.TestCase):
    def test_theil_sen_growth_ignores_single_sample_spike(self) -> None:
        measured = samples([100, 101, 140, 102, 103])
        self.assertAlmostEqual(theil_sen_slope(measured), (17 / 24) * MIB)
        report = summarize(measured, threshold_mib=10)
        self.assertTrue(report["budget_passed"])
        self.assertGreater(report["maximum_rss_mib"] - report["minimum_rss_mib"], 10)

    def test_sustained_growth_over_budget_fails(self) -> None:
        report = summarize(samples([100, 104, 108, 112, 116]), threshold_mib=10)
        self.assertFalse(report["budget_passed"])
        self.assertEqual(report["theil_sen_growth_mib"], 16.0)

    def test_flat_or_declining_process_passes(self) -> None:
        self.assertEqual(summarize(samples([100, 98, 99, 97]), 10)["theil_sen_growth_mib"], 0.0)

    def test_summary_requires_sufficient_samples_and_time_span(self) -> None:
        with self.assertRaises(ValueError):
            summarize(samples([100, 101]), 10)
        with self.assertRaises(ValueError):
            summarize([
                {"elapsed_seconds": 0.0, "rss_bytes": 100 * MIB},
                {"elapsed_seconds": 0.0, "rss_bytes": 101 * MIB},
                {"elapsed_seconds": 0.0, "rss_bytes": 102 * MIB},
            ], 10)


if __name__ == "__main__":
    unittest.main()
