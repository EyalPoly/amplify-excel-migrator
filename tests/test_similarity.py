from amplify_excel_migrator.data.similarity import closest


def test_ranks_the_closest_match_first():
    result = closest("Kiryat Haim", ["Qiryat Hayyim Beach", "Tel Aviv Port", "Kiryat Haym"])
    assert result[0][0] == "Kiryat Haym"


def test_returns_name_score_pairs_sorted_by_score_desc():
    result = closest("apple", ["apple", "apples", "orange"])
    names = [name for name, _ in result]
    scores = [score for _, score in result]
    assert names[0] == "apple"
    assert scores == sorted(scores, reverse=True)


def test_respects_k_limit():
    result = closest("a", ["a", "ab", "abc", "abcd", "abcde", "abcdef"], k=2)
    assert len(result) == 2


def test_empty_when_nothing_clears_cutoff():
    assert closest("zzzzzzzzz", ["apple", "orange"], cutoff=0.9) == []


def test_matching_is_case_insensitive_but_returns_original_name():
    result = closest("PANTHERA", ["panthera"])
    assert result[0][0] == "panthera"
    assert result[0][1] == 1.0


def test_empty_candidates_returns_empty():
    assert closest("anything", []) == []
