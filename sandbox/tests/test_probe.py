import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe import GUEST_PROBE, containment_acceptance_fields


class ProbeAcceptanceTests(unittest.TestCase):
    def test_guest_probe_payload_remains_valid_python(self):
        compile(GUEST_PROBE, '<guest-probe>', 'exec')

    def test_missing_ipv6_route_or_canary_evidence_cannot_complete_acceptance(self):
        fields = containment_acceptance_fields({'observed_checks_passed': True})

        self.assertEqual(fields['ipv6_containment_status'], 'unverified')
        self.assertFalse(fields['full_network_containment_proven'])
        self.assertFalse(fields['acceptance_complete'])

    def test_route_without_blocked_canary_cannot_complete_acceptance(self):
        fields = containment_acceptance_fields({
            'observed_checks_passed': True,
            'ipv6_active_route_verified': True,
        })

        self.assertEqual(fields['ipv6_containment_status'], 'unverified')
        self.assertFalse(fields['acceptance_complete'])

    def test_configured_ipv6_route_and_failed_public_connection_are_not_canary_proof(self):
        fields = containment_acceptance_fields({
            'observed_checks_passed': True,
            'ipv6_default_route_observed': True,
            'public_ipv6_connection_failed': True,
        })

        self.assertEqual(fields['ipv6_containment_status'], 'unverified')
        self.assertFalse(fields['full_network_containment_proven'])
        self.assertFalse(fields['acceptance_complete'])

    def test_missing_ipv6_default_route_is_reported_as_inconclusive(self):
        fields = containment_acceptance_fields({
            'observed_checks_passed': True,
            'ipv6_default_route_observed': False,
            'public_ipv6_connection_failed': True,
        })

        self.assertEqual(fields['ipv6_containment_status'], 'unverified')
        self.assertIn('no configured IPv6 default route', fields['ipv6_containment_reason'])
        self.assertFalse(fields['acceptance_complete'])

    def test_full_acceptance_requires_observations_and_positive_ipv6_filter_evidence(self):
        evidence = {
            'observed_checks_passed': True,
            'ipv6_active_route_verified': True,
            'ipv6_canary_blocked': True,
        }

        fields = containment_acceptance_fields(evidence)

        self.assertEqual(fields['ipv6_containment_status'], 'verified_blocked')
        self.assertIsNone(fields['ipv6_containment_reason'])
        self.assertTrue(fields['full_network_containment_proven'])
        self.assertTrue(fields['acceptance_complete'])

    def test_ipv6_evidence_cannot_override_a_failed_existing_check(self):
        fields = containment_acceptance_fields({
            'observed_checks_passed': False,
            'ipv6_active_route_verified': True,
            'ipv6_canary_blocked': True,
        })

        self.assertTrue(fields['ipv6_containment_status'] == 'verified_blocked')
        self.assertFalse(fields['full_network_containment_proven'])
        self.assertFalse(fields['acceptance_complete'])


if __name__ == '__main__':
    unittest.main()
