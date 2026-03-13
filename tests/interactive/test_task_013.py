from __future__ import annotations

import unittest

from tests.interactive.boot_payload_schema import (
    BOOT_PAYLOAD_SCHEMA_PATH,
    InteractiveBootPayloadSchemaNotFound,
    load_boot_payload_sample,
    load_boot_payload_schema,
    validate_boot_payload_against_schema,
)


class Task013BootPayloadSchemaTests(unittest.TestCase):
    def test_green_boot_payload_schema_accepts_fixture_backed_sample(self) -> None:
        schema = load_boot_payload_schema()
        sample = load_boot_payload_sample()

        self.assertEqual(schema.path, BOOT_PAYLOAD_SCHEMA_PATH)
        self.assertEqual(schema.version, "1.0.0")
        self.assertEqual(
            schema.required_top_level_keys,
            [
                "version",
                "route",
                "session",
                "interactive_session",
                "runtime_identity",
                "artifact",
                "tail",
                "replay",
            ],
        )
        self.assertEqual(
            schema.capability_transport_values,
            ["codex_app_server", "codex_exec_json", "codex_sdk_ts"],
        )
        self.assertEqual(
            schema.runtime_transport_values,
            ["codex_app_server", "codex_exec_json", "codex_sdk_ts"],
        )
        self.assertEqual(
            schema.runtime_source_values,
            ["fixture", "operational_live", "recovered"],
        )
        self.assertTrue(validate_boot_payload_against_schema(sample, schema))

    def test_red_rejects_unknown_interactive_transport(self) -> None:
        schema = load_boot_payload_schema()
        sample = load_boot_payload_sample()
        sample["interactive_session"]["transport"] = "qemu_web"

        self.assertFalse(validate_boot_payload_against_schema(sample, schema))

    def test_red_missing_schema_fails_honestly(self) -> None:
        with self.assertRaises(InteractiveBootPayloadSchemaNotFound):
            load_boot_payload_schema(
                schema_path=BOOT_PAYLOAD_SCHEMA_PATH.parent / "missing-interactive-boot-payload.schema.json"
            )


if __name__ == "__main__":
    unittest.main()
