from app.services.mfa import (
    build_backup_code_entries,
    count_unused_backup_codes,
    generate_backup_codes,
    hash_backup_code,
    match_backup_code,
)


class TestGenerateBackupCodes:
    def test_default_count_and_format(self):
        codes = generate_backup_codes()
        assert len(codes) == 10
        for c in codes:
            # 5文字-5文字（ハイフン区切り）
            assert len(c) == 11 and c[5] == "-"

    def test_codes_are_unique_across_generation(self):
        codes = generate_backup_codes(20)
        assert len(set(codes)) == 20

    def test_two_generations_differ(self):
        assert generate_backup_codes(5) != generate_backup_codes(5)

    def test_excludes_ambiguous_characters(self):
        # I / L / O / U は誤読防止のため使わない
        joined = "".join(generate_backup_codes(30)).replace("-", "")
        assert not (set("ILOU") & set(joined))


class TestHashBackupCode:
    def test_is_sha256_hex(self):
        h = hash_backup_code("ABCDE-12345")
        assert len(h) == 64
        int(h, 16)  # 16進としてパースできる

    def test_normalizes_case_spacing_and_hyphen(self):
        base = hash_backup_code("ABCDE-12345")
        assert hash_backup_code("abcde-12345") == base
        assert hash_backup_code("ABCDE12345") == base
        assert hash_backup_code("  ABCDE-12345  ") == base

    def test_different_codes_differ(self):
        assert hash_backup_code("ABCDE-12345") != hash_backup_code("ABCDE-12346")


class TestMatchAndCount:
    def test_match_returns_index_of_unused_entry(self):
        codes = generate_backup_codes(3)
        entries = build_backup_code_entries(codes)
        assert match_backup_code(entries, codes[1]) == 1

    def test_match_is_case_and_format_insensitive(self):
        codes = generate_backup_codes(2)
        entries = build_backup_code_entries(codes)
        assert match_backup_code(entries, codes[0].lower().replace("-", "")) == 0

    def test_used_entries_are_not_matched(self):
        codes = generate_backup_codes(2)
        entries = build_backup_code_entries(codes)
        entries[0]["used"] = True
        assert match_backup_code(entries, codes[0]) is None
        assert match_backup_code(entries, codes[1]) == 1

    def test_unknown_code_and_empty_entries(self):
        entries = build_backup_code_entries(generate_backup_codes(2))
        assert match_backup_code(entries, "ZZZZZ-99999") is None
        assert match_backup_code(None, "ZZZZZ-99999") is None
        assert match_backup_code([], "ZZZZZ-99999") is None

    def test_entries_store_hash_not_plaintext(self):
        codes = generate_backup_codes(2)
        entries = build_backup_code_entries(codes)
        serialized = str(entries)
        for c in codes:
            assert c not in serialized  # 平文は保存されない
            assert hash_backup_code(c) in serialized

    def test_count_unused(self):
        entries = build_backup_code_entries(generate_backup_codes(4))
        assert count_unused_backup_codes(entries) == 4
        entries[0]["used"] = True
        entries[2]["used"] = True
        assert count_unused_backup_codes(entries) == 2
        assert count_unused_backup_codes(None) == 0
        assert count_unused_backup_codes([]) == 0
