from core.spacy_utils import *
from core.utils.models import _3_1_SPLIT_BY_NLP
from core.utils import check_file_exists
from translations.translations import translate as t

@check_file_exists(_3_1_SPLIT_BY_NLP)
def split_by_spacy(progress_callback=None):
    def _report(pct, key):
        if progress_callback:
            try:
                progress_callback(step="nlp", detail=t(key), percent=pct)
            except Exception:
                pass
    nlp = init_nlp()
    _report(5, "nlp_mark")
    split_by_mark(nlp)
    _report(35, "nlp_comma")
    split_by_comma_main(nlp)
    _report(65, "nlp_sentence")
    split_sentences_main(nlp)
    _report(90, "nlp_root")
    split_long_by_root_main(nlp)
    _report(100, "nlp_done")
    return

if __name__ == '__main__':
    split_by_spacy()