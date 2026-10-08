# ====== Code Summary ======
# The French + English stopword set of the local BM25 sparse provider (bm25_local). Words are stored ALREADY
# accent-folded and lowercased, because the analyzer folds before it filters (so "été" is "ete",
# "à" is "a"). Kept deliberately short — function words only — so a domain term is never dropped.
# Changing this set changes the encoding: it is part of the versioned ``bm25_v1`` contract.

FRENCH_STOPWORDS: frozenset[str] = frozenset(
    """
    a au aux avec c ce ces cet cette d dans de des du elle elles en es est et etre ete eu eux il ils
    j je l la le les leur leurs lui m ma mais me meme mes moi mon n ne nos notre nous on ou par pas
    pour qu que quel quelle qui s sa sans se ses si son sont sur t ta te tes toi ton tu un une vos
    votre vous y
    """.split()
)

ENGLISH_STOPWORDS: frozenset[str] = frozenset(
    """
    a an and are as at be been being but by can did do does for from had has have he her his i if
    in into is it its me my no nor not of on or our she so such than that the their them then there
    these they this those to too was we were what when which who will with you your
    """.split()
)

BM25_STOPWORDS: frozenset[str] = FRENCH_STOPWORDS | ENGLISH_STOPWORDS

__all__ = ["FRENCH_STOPWORDS", "ENGLISH_STOPWORDS", "BM25_STOPWORDS"]
